#!/usr/bin/env python3
"""
tri_photos.py
Trie les photos d'un dossier (copie de ton téléphone) :
  - doublons exacts         -> A_verifier/doublons_exacts
  - quasi-doublons          -> A_verifier/quasi_doublons   (la meilleure reste en place)
  - photos inutiles (IA)    -> A_verifier/inutiles
  - WhatsApp                -> WhatsApp/AAAA-MM
  - voyages (loin de Brașov)-> Voyages/AAAA-MM-JJ_Pays_Ville
  - le reste                -> Autres/AAAA-MM
Ne supprime JAMAIS rien et ne modifie JAMAIS les métadonnées.
"""
import argparse
import base64
import hashlib
import html
import io
import os
import re
import shutil
import time
import json
import sys 
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import cv2
import imagehash
import numpy as np
import open_clip
import pillow_heif
import reverse_geocoder as rg
import torch
from PIL import Image

pillow_heif.register_heif_opener()  # HEIC (iPhone, et certains Android)

IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp"}
VID_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".avi"}
WA_RE = re.compile(r"WA\d{4}", re.IGNORECASE)
GAP_JOURS = 3
MIN_PHOTOS_VOYAGE = 10  # en dessous, les photos vont dans Autres
SEUIL_SOMBRE = 10  # luminosité moyenne sous laquelle la photo est jugée noire (0 à 255)

PAYS = {"ES": "Espagne", "FR": "France", "IT": "Italie", "DE": "Allemagne",
        "GB": "Royaume-Uni", "US": "Etats-Unis", "PT": "Portugal", "GR": "Grece",
        "TR": "Turquie", "HU": "Hongrie", "AT": "Autriche", "CH": "Suisse",
        "BE": "Belgique", "NL": "Pays-Bas", "RO": "Roumanie", "BG": "Bulgarie",
        "MA": "Maroc", "TH": "Thailande", "JP": "Japon"}

# Libellés CLIP : les premiers = "inutile", les suivants = "utile"
INUTILE = ["a photo of a whiteboard or blackboard with writing",
           "a photo of a sheet of paper or a document",
           "a screenshot of a computer screen or a spreadsheet",
           "a photo of a receipt or a ticket",
           "a screenshot of a phone screen, an app or a chat conversation",
           "a photo of textbook pages or handwritten notes"]
UTILE = ["a photo of a person", "a photo of a landscape or nature",
         "a photo of an animal", "a photo of food",
         "a photo of a building or monument", "a photo of a city street",
         "a photo of friends or family together"]
LABELS = INUTILE + UTILE

POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)

CONFIG_LIEUX = Path(__file__).with_name("lieux.json")


def charger_config():
    """Lit lieux.json : rayon en km et liste (nom, lat, lon)."""
    if not CONFIG_LIEUX.exists():
        return 50, []
    d = json.loads(CONFIG_LIEUX.read_text(encoding="utf-8"))
    lieux = [(re.sub(r'[<>:"/\\|?*]', "", l["nom"]), l["lat"], l["lon"])
             for l in d.get("lieux", [])]
    return d.get("rayon_km", 50), lieux


DIST_VOYAGE_KM, LIEUX_DE_VIE = charger_config()


# ---------- Lecture des métadonnées (lecture seule) ----------

def date_exif(exif):
    try:
        ifd = exif.get_ifd(0x8769)  # Exif IFD
        s = ifd.get(36867) or ifd.get(36868) or exif.get(306)
        return datetime.strptime(str(s)[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def gps_exif(exif):
    try:
        g = exif.get_ifd(0x8825)  # GPSInfo

        def conv(v, ref):
            val = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -val if str(ref).upper().startswith(("S", "W")) else val

        return conv(g[2], g[1]), conv(g[4], g[3])
    except Exception:
        return None


def haversine(a, b):
    R = 6371
    la1, lo1 = map(radians, a)
    la2, lo2 = map(radians, b)
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * R * asin(sqrt(h))


# ---------- Analyse (exécutée en parallèle sur les cœurs CPU) ----------

def analyser(chemin):
    p = Path(chemin)
    r = {"path": chemin, "ext": p.suffix.lower(), "sha": None, "phash": None,
         "nettete": 0.0, "pixels": 0, "date": None, "date_exif": None, "gps": None,
         "taille": (0, 0), "camera": False, "luminosite": 255.0,
         "wa": bool(WA_RE.search(p.name)) or "whatsapp" in chemin.lower()}
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        r["sha"] = h.hexdigest()
        st = p.stat()
        # Date de référence : la plus ancienne entre création et modification
        r["date"] = min(datetime.fromtimestamp(st.st_ctime),
                        datetime.fromtimestamp(st.st_mtime))
    except OSError:
        return r
    if r["ext"] in VID_EXT:
        return r
    try:
        with Image.open(p) as im:
            exif = im.getexif()
            r["date_exif"] = date_exif(exif)
            if r["date_exif"]:
                r["date"] = r["date_exif"]
            r["gps"] = gps_exif(exif)
            r["pixels"] = im.width * im.height
            r["taille"] = (im.width, im.height)
            r["camera"] = bool(exif.get(271))  # 271 = marque de l'appareil
            rgb = im.convert("RGB")
        rgb.thumbnail((1024, 1024))
        r["phash"] = str(imagehash.phash(rgb))
        gris = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY)
        r["luminosite"] = float(gris.mean())
        r["nettete"] = float(cv2.Laplacian(gris, cv2.CV_64F).var())
    except Exception:
        pass
    return r


# ---------- Classification « inutile » par CLIP (GPU) ----------

class Jeu(torch.utils.data.Dataset):
    def __init__(self, chemins, pre):
        self.chemins, self.pre = chemins, pre

    def __len__(self):
        return len(self.chemins)

    def __getitem__(self, i):
        try:
            with Image.open(self.chemins[i]) as im:
                im = im.convert("RGB")
                im.thumbnail((512, 512))  # CLIP n'utilise que 224 px : inutile de garder plus grand
                return self.pre(im)
        except Exception:
            return torch.zeros(3, 224, 224)


def scorer_clip(recs, device):
    """Retourne, pour chaque image, la probabilité de chaque libellé (LABELS)."""
    if not recs:
        return []
    model, _, pre = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k")
    tok = open_clip.get_tokenizer("ViT-B-32")
    model = model.to(device).eval()
    amp = torch.autocast(device_type="cuda", enabled=device == "cuda")
    with torch.no_grad(), amp:
        txt = model.encode_text(tok(LABELS).to(device)).float()
        txt = txt / txt.norm(dim=-1, keepdim=True)
    dl = torch.utils.data.DataLoader(
        Jeu([r["path"] for r in recs], pre),
        batch_size=128,                              # lots plus gros
        num_workers=min(8, os.cpu_count() or 4),     # plus de décodage en parallèle
        pin_memory=(device == "cuda"),               # transfert CPU -> GPU plus rapide
        persistent_workers=True,
    )
    resultats = []
    debut = time.time()
    with torch.no_grad(), amp:
        for i, x in enumerate(dl):
            img = model.encode_image(x.to(device, non_blocking=True)).float()
            img = img / img.norm(dim=-1, keepdim=True)
            probs = (100 * img @ txt.T).softmax(dim=-1)
            resultats.append(probs.cpu())
            if i % 20 == 0:
                vitesse = (i + 1) * 128 / (time.time() - debut)
                print(f"  IA : {min((i + 1) * 128, len(recs))}/{len(recs)} "
                      f"({vitesse:.0f} img/s)")
    return torch.cat(resultats).tolist()


# ---------- Doublons quasi identiques ----------

def trouver_groupes(recs, seuil):
    n = len(recs)
    if n < 2:
        return []
    H = np.array([np.frombuffer(bytes.fromhex(r["phash"]), dtype=np.uint8) for r in recs])
    parent = list(range(n))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n - 1):
        d = POP[np.bitwise_xor(H[i + 1:], H[i])].sum(axis=1)
        for j in np.nonzero(d <= seuil)[0]:
            a, b = racine(i), racine(i + 1 + int(j))
            if a != b:
                parent[a] = b
    groupes = defaultdict(list)
    for i, r in enumerate(recs):
        groupes[racine(i)].append(r)
    return [g for g in groupes.values() if len(g) > 1]


def meilleure(groupe):
    candidats = [r for r in groupe if not est_sombre(r)] or groupe
    mp = max(r["pixels"] for r in candidats) or 1
    mn = max(r["nettete"] for r in candidats) or 1
    return max(candidats, key=lambda r: 0.5 * r["pixels"] / mp + 0.5 * r["nettete"] / mn)


# ---------- Voyages ----------

def lieu_de_vie(gps):
    """Retourne le nom du lieu de vie le plus proche (dans le rayon), sinon None."""
    proches = [(haversine(gps, (lat, lon)), nom)
               for nom, lat, lon in LIEUX_DE_VIE]
    dist, nom = min(proches)
    return nom if dist <= DIST_VOYAGE_KM else None

def loin_de_tout(gps):
    return lieu_de_vie(gps) is None

def a_metadonnees(r):
    """Métadonnées = coordonnées GPS ou date de prise de vue EXIF."""
    return bool(r.get("gps")) or bool(r.get("date_exif"))

def sujet_detecte(r):
    """CLIP a détecté une personne, un paysage ou un animal (probabilité > 0,5)."""
    return r.get("p_sujet", 0.0) > 0.5

def est_capture(r):
    chemin = r["path"].lower()
    if "screenshot" in chemin or "capture" in chemin:
        return True
    if r.get("camera"):
        return False  # une vraie photo de l'appareil n'est pas une capture
    w, h = r["taille"]
    if not w or not h:
        return False
    # écrans de téléphone récents : ratio ~2.0 à 2.4 ; photos normales : ≤ 1.8
    return max(w, h) / min(w, h) >= 1.95

def est_sombre(r):
    return r.get("luminosite", 255.0) < SEUIL_SOMBRE

def est_aiselect(r):
    return "aiselect" in Path(r["path"]).name.lower()

    
def est_snap_clip(r):
    c = r["path"].lower()
    return "snapchat" in c or "clipped" in c

def voyage_wa(r, periodes):
    """Retourne le nom du voyage si la photo WhatsApp est dans sa période + 2 jours."""
    d = r["date"].date()
    for debut, fin, nom in periodes:
        if debut.date() <= d <= (fin + timedelta(days=2)).date():
            return nom
    return None

def trouver_voyages(recs):
    """Seules les photos géolocalisées loin de tous les lieux de vie créent un voyage.
    Retourne (affectation {chemin: nom}, periodes [(debut, fin, nom)])."""
    loin = sorted([r for r in recs if r["date"] and r["gps"] and loin_de_tout(r["gps"])],
                  key=lambda r: r["date"])
    grappes, cur = [], []
    for r in loin:
        if cur and r["date"] - cur[-1]["date"] > timedelta(days=GAP_JOURS):
            grappes.append(cur)
            cur = []
        cur.append(r)
    if cur:
        grappes.append(cur)
    grappes = [g for g in grappes if len(g) >= MIN_PHOTOS_VOYAGE]
    if not grappes:
        return {}, []

    tous = [r for g in grappes for r in g]
    geo = rg.search([r["gps"] for r in tous], mode=1)
    lieu = {r["path"]: x for r, x in zip(tous, geo)}

    affectation, periodes, compteur = {}, [], Counter()
    for g in grappes:
        cc, ville = Counter(
            (lieu[r["path"]]["cc"], lieu[r["path"]]["name"] or "Ville_inconnue")
            for r in g
        ).most_common(1)[0][0]
        debut, fin = g[0]["date"], g[-1]["date"]
        nom = re.sub(r'[<>:"/\\|?*]', "", f"{debut:%Y-%m-%d}_{PAYS.get(cc, cc)}_{ville}")
        compteur[nom] += 1
        if compteur[nom] > 1:
            nom += f"_{compteur[nom]}"
        periodes.append((debut, fin, nom))
        for r in g:
            affectation[r["path"]] = nom
    return affectation, periodes


# ---------- Rapport visuel ----------

def miniature(chemin):
    try:
        with Image.open(chemin) as im:
            im = im.convert("RGB")
            im.thumbnail((220, 220))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def ecrire_rapport(groupes, fichier):
    blocs = []
    for i, (titre, membres, gardee) in enumerate(groupes, 1):
        figs = []
        for r in membres:
            cls = "garde" if r["path"] == gardee["path"] else ""
            taille = Path(r["path"]).stat().st_size / 1e6
            figs.append(
                f'<figure class="{cls}"><img src="{miniature(r["path"])}">'
                f'<figcaption>{html.escape(Path(r["path"]).name)}<br>'
                f'{r["pixels"] / 1e6:.1f} Mpx · netteté {r["nettete"]:.0f} · {taille:.1f} Mo'
                f'{" · <b>À GARDER</b>" if cls else ""}</figcaption></figure>')
        blocs.append(f"<div class='g'><h3>{i}. {titre}</h3>{''.join(figs)}</div>")
    doc = ("<!doctype html><html lang='fr'><meta charset='utf-8'><title>Doublons</title>"
           "<style>body{font-family:sans-serif;background:#111;color:#eee}"
           ".g{border:1px solid #444;margin:16px;padding:10px}"
           "figure{display:inline-block;margin:6px;width:240px;vertical-align:top;"
           "background:#222;padding:6px}figure.garde{outline:4px solid #2e9e44}"
           "img{max-width:220px;max-height:220px}figcaption{font-size:12px}</style>"
           f"<body><h1>{len(groupes)} groupes de doublons</h1>{''.join(blocs)}</body></html>")
    fichier.write_text(doc, encoding="utf-8")


# ---------- Programme principal ----------

def unique(p):
    if not p.exists():
        return p
    i = 1
    while True:
        c = p.with_name(f"{p.stem}_{i}{p.suffix}")
        if not c.exists():
            return c
        i += 1


def main():
    global DIST_VOYAGE_KM, LIEUX_DE_VIE
    ap = argparse.ArgumentParser(description="Tri de photos (sans suppression)")
    ap.add_argument("source", nargs="?", default="DCIM",
                    help="dossier des photos (à côté du script)")
    ap.add_argument("sortie", nargs="?", default="Tri_Photos",
                    help="dossier de sortie (à côté du script)")
    ap.add_argument("--deplacer", action="store_true", help="déplacer au lieu de copier")
    ap.add_argument("--simuler", action="store_true", help="rapport seulement, rien n'est copié")
    ap.add_argument("--seuil-inutile", type=float, default=0.8, help="exigence (plus haut = plus exigeant)")
    ap.add_argument("--seuil-doublon", type=int, default=4, help="distance pHash max (plus bas = plus strict)")
    a = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Calcul IA sur : {device}")
    dossier = Path(__file__).resolve().parent
    src, sortie = dossier / a.source, dossier / a.sortie
    if not src.is_dir():
        sys.exit(f"ERREUR : le dossier '{a.source}' est introuvable. "
                 f"Il doit se trouver dans {dossier}")
    if not LIEUX_DE_VIE:
        print("Aucun lieu de vie enregistré : ouverture de la fenêtre de configuration.")
        import lieux_de_vie
        lieux_de_vie.main()
        DIST_VOYAGE_KM, LIEUX_DE_VIE = charger_config()
    sortie.mkdir(parents=True, exist_ok=True)

    fichiers = [str(p) for p in src.rglob("*")
                if p.suffix.lower() in IMG_EXT | VID_EXT and sortie not in p.parents]
    print(f"{len(fichiers)} fichiers trouvés, analyse en cours...")

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        recs = list(ex.map(analyser, fichiers, chunksize=32))

    # 1. Doublons exacts : on ne garde qu'un représentant par contenu
    par_sha = defaultdict(list)
    for r in recs:
        if r["sha"]:
            par_sha[r["sha"]].append(r)
    reps = [v[0] for v in par_sha.values()]
    imgs = [r for r in reps if r["ext"] in IMG_EXT]

    # 2. IA : probabilité « inutile »
    print("Classification IA...")
    for r in imgs:
        r["p_inutile"] = 0.0
        r["p_sujet"] = 0.0
    for r, pr in zip(imgs, scorer_clip(imgs, device)):
        r["p_inutile"] = sum(pr[:len(INUTILE)])
        # les 3 premiers libellés « utile » : personne, paysage, animal
        r["p_sujet"] = max(pr[len(INUTILE):len(INUTILE) + 3])

    # 3. Quasi-doublons
    groupes_quasi = trouver_groupes([r for r in imgs if r["phash"]], a.seuil_doublon)

    garde_de, extras, notes = {}, [], defaultdict(list)
    groupes_rapport = []
    for g in groupes_quasi:
        best = meilleure(g)
        groupes_rapport.append(("Quasi-doublons", g, best))
        for r in g:
            garde_de[r["path"]] = best["path"]
            if r is not best:
                extras.append((r, "A_verifier/quasi_doublons"))
                notes[best["path"]].append(("quasi", r["path"]))
    for v in par_sha.values():
        if len(v) > 1:
            groupes_rapport.append(("Doublons exacts", v, v[0]))
        cible = garde_de.get(v[0]["path"], v[0]["path"])
        for d in v[1:]:
            extras.append((d, "A_verifier/doublons_exacts"))
            notes[cible].append(("exact", d["path"]))

    # 4. Placement des photos restantes
    extras_set = {r["path"] for r, _ in extras}
    restantes = [r for r in reps if r["path"] not in extras_set]

    def est_inutile(r):
        return r.get("p_inutile", 0) >= a.seuil_inutile
    
    candidats = [r for r in restantes
                 if not (est_inutile(r) or est_sombre(r) or est_aiselect(r)
                         or est_capture(r) or est_snap_clip(r) or r["wa"])]
    voyages, periodes = trouver_voyages(candidats)

    plan = list(extras)
    for r in restantes:
        if est_aiselect(r):
            d = "A_verifier/AiSelect"
        elif est_sombre(r):
            d = "A_verifier/trop_sombres"
        elif est_inutile(r):
            d = "A_verifier/inutiles"
        elif r.get("gps") and lieu_de_vie(r["gps"]):
            d = lieu_de_vie(r["gps"])
        elif r["path"] in voyages:
            d = f"Voyages/{voyages[r['path']]}"
        elif not a_metadonnees(r) and voyage_wa(r, periodes):
            d = f"Voyages/{voyage_wa(r, periodes)}_Whatsapp"
        elif est_snap_clip(r):
            d = "Snapchat_Clipped"
        elif est_capture(r):
            d = "Autres" if sujet_detecte(r) else "Captures"
        elif r["date"] is None:
            d = "Inconnu"
        elif r["wa"] and not a_metadonnees(r):
            d = "WhatsApp"
        else:
            d = "Autres"
        plan.append((r, d))

    dossier_de = {r["path"]: d for r, d in plan}
    print("\nRésumé :")
    for cle, n in Counter(d.split("/")[0] + "/" + d.split("/")[1]
                          if "/" in d else d for _, d in plan).most_common():
        print(f"  {cle:<40} {n}")
    print(f"  Groupes de doublons : {len(groupes_rapport)}")

    ecrire_rapport(groupes_rapport, sortie / "rapport_doublons.html")
    if a.simuler:
        print(f"\nSimulation terminée. Voir {sortie / 'rapport_doublons.html'}")
        return

    # 5. Copie ou déplacement (les métadonnées ne sont pas modifiées)
    dest_de = {}
    for r, d in plan:
        dest_dir = sortie / d
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = unique(dest_dir / Path(r["path"]).name)
        (shutil.move if a.deplacer else shutil.copy2)(r["path"], dest)
        dest_de[r["path"]] = dest

    # 6. Fichier « à ne pas supprimer » dans le dossier de la meilleure photo
    for chemin, lignes in notes.items():
        fichier = dest_de[chemin].parent / "A_NE_PAS_SUPPRIMER.txt"
        with open(fichier, "a", encoding="utf-8") as f:
            f.write(f"GARDER : {dest_de[chemin].name}\n")
            for type_, p in lignes:
                f.write(f"   - doublon {type_} : {Path(p).name}\n")
            f.write("\n")

    print(f"\nTerminé. Ouvre {sortie / 'rapport_doublons.html'} pour comparer les doublons.")


if __name__ == "__main__":
    main()