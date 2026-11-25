#!/usr/bin/env python3
"""
interface_tri.py
Révision du tri : navigation dans Tri_Photos, sélection multiple, déplacement,
puis validation (originaux envoyés à la Corbeille).
Ne supprime rien sans confirmation.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
import queue
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk



from PIL import Image, ImageDraw, ImageOps, ImageTk
import pillow_heif

try:
    from send2trash import send2trash
except ImportError:
    sys.exit("Le module send2trash est absent. Lance : python -m pip install send2trash")

from manifeste import charger as charger_manifeste, sauver as sauver_manifeste

pillow_heif.register_heif_opener()

ICI = Path(__file__).resolve().parent
DCIM = ICI / "DCIM"
TRI = ICI / "Tri_Photos"
MINI = TRI / ".miniatures"
ATTENTE = "A_verifier"
IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp"}
VID_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".avi"}
MEDIA = IMG_EXT | VID_EXT
TAILLE_MINI = (160, 110)


# ---------- Fonctions utilitaires ----------

def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def est_video(p):
    return p.suffix.lower() in VID_EXT


def cacher(p):
    if sys.platform == "win32":
        subprocess.run(["attrib", "+h", str(p)], capture_output=True)


def unique(p):
    if not p.exists():
        return p
    i = 1
    while True:
        c = p.with_name(f"{p.stem}_{i}{p.suffix}")
        if not c.exists():
            return c
        i += 1


def visible(p):
    """Vrai si le chemin, dans Tri_Photos, n'est pas caché ni dans un dossier caché."""
    return not any(part.startswith(".") for part in p.relative_to(TRI).parts)


def photos_dans(dossier):
    return sorted(p for p in dossier.iterdir() if p.is_file() and p.suffix.lower() in MEDIA)


def fichiers_tri():
    """Photos et vidéos de Tri_Photos, sans entrer dans les dossiers cachés."""
    trouves = []
    for dossier, sous, fichiers in os.walk(TRI):
        sous[:] = [d for d in sous if not d.startswith(".")]
        for nom in fichiers:
            if not nom.startswith(".") and Path(nom).suffix.lower() in MEDIA:
                trouves.append(Path(dossier) / nom)
    return trouves


def lister_dossiers():
    """Chemins relatifs des dossiers visibles ; '.' désigne la racine."""
    dossiers = []
    for dossier, sous, _ in os.walk(TRI):
        sous[:] = [d for d in sous if not d.startswith(".")]
        for d in sous:
            dossiers.append((Path(dossier) / d).relative_to(TRI).as_posix())
    return ["."] + sorted(dossiers)

def empreintes(chemins):
    """SHA-256 de plusieurs fichiers en parallèle, dans le même ordre."""
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(empreinte, chemins))

def nom_dossier(d):
    return "Tri_Photos" if d == TRI else "Tri_Photos/" + d.relative_to(TRI).as_posix()


def index_dcim():
    """Fichiers de DCIM groupés par taille (évite de tout hacher)."""
    index = defaultdict(list)
    if DCIM.is_dir():
        for c in DCIM.rglob("*"):
            if c.is_file() and c.suffix.lower() in MEDIA:
                index[c.stat().st_size].append(c)
    return index


def cle_miniature(p):
    st = p.stat()
    brut = f"{p.name}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.md5(brut.encode("utf-8")).hexdigest()


def generer_miniature(p):
    if not est_video(p):
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail(TAILLE_MINI)
                return im.copy()
        except Exception:
            pass
    img = Image.new("RGB", TAILLE_MINI, (55, 55, 55))
    texte = "VIDEO" if est_video(p) else "Aperçu indisponible"
    ImageDraw.Draw(img).text((8, 40), texte, fill=(230, 230, 230))
    return img


def preparer_suppression():
    """Calcule ce qui serait supprimé. Ne touche à rien."""
    dossier = TRI / ATTENTE
    if not dossier.is_dir():
        return dossier, [], [], 0
    copies = [p for p in dossier.rglob("*") if p.is_file()]
    if not copies:
        return dossier, [], [], 0
    compte = Counter(empreintes(copies))

    index = index_dcim()
    tailles = {p.stat().st_size for p in copies}
    candidats = [c for t in tailles for c in index.get(t, [])]
    originaux = defaultdict(list)
    for c, sha in zip(candidats, empreintes(candidats)):
        originaux[sha].append(c)

    a_retirer, manquants = [], 0
    for sha, k in compte.items():
        dispo = originaux.get(sha, [])
        n = min(k, len(dispo))
        manquants += k - n
        a_retirer.extend(dispo[:n])
    return dossier, copies, a_retirer, manquants


def supprimer(dossier, a_retirer):
    """Envoie les originaux de DCIM, puis le dossier A_verifier, à la Corbeille."""
    for p in a_retirer:
        send2trash(str(p))
    if dossier.exists():
        send2trash(str(dossier))


# ---------- Fenêtre de choix de dossier ----------

class ChoixDossier(tk.Toplevel):
    def __init__(self, parent, dossiers):
        super().__init__(parent)
        self.title("Déplacer vers…")
        self.transient(parent)
        self.resultat = None
        self.dossiers = dossiers

        ttk.Label(self, text="Dossier de destination :").pack(anchor="w", padx=10, pady=(10, 4))
        self.liste = tk.Listbox(self, width=55, height=20)
        for d in dossiers:
            self.liste.insert("end", "(racine Tri_Photos)" if d == "." else d)
        self.liste.pack(fill="both", expand=True, padx=10)
        self.liste.bind("<Double-1>", lambda e: self._ok())

        ligne = ttk.Frame(self)
        ligne.pack(pady=10)
        ttk.Button(ligne, text="Déplacer ici", command=self._ok).pack(side="left", padx=4)
        ttk.Button(ligne, text="Annuler", command=self.destroy).pack(side="left", padx=4)

        self.wait_visibility()
        self.grab_set()
        self.wait_window()

    def _ok(self):
        sel = self.liste.curselection()
        if sel:
            self.resultat = self.dossiers[sel[0]]
        self.destroy()


# ---------- Application ----------

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tri de photos : révision")
        self.geometry("1200x780")
        self.minsize(900, 560)
        self.data = charger_manifeste(TRI, DCIM)
        self.modifie = False
        self.dossier = TRI
        self._affiche = None
        self.presse = None
        self.index_dcim = None
        self.miniatures = {}
        self.comptes = Counter()
        self.generation = 0
        self.futurs = []
        self.file_mini = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=4)
        MINI.mkdir(parents=True, exist_ok=True)
        cacher(MINI)

        # chemin -> (sha256, taille, mtime)
        self.sha_par_chemin = {}
        for sha, v in self.data.get("photos", {}).items():
            f = TRI / v.get("fichier", "")
            if f.is_file() and f.stat().st_size == v.get("taille"):
                self._memoriser(f, sha)

        self._construire()
        self._rafraichir()
        self.after(50, self._traiter_miniatures)
        self.protocol("WM_DELETE_WINDOW", self.quitter)

    # --- Construction de l'interface ---

    def _construire(self):
        ttk.Style(self).configure("Treeview", rowheight=TAILLE_MINI[1] + 14)

        barre = ttk.Frame(self, padding=(8, 6))
        barre.pack(fill="x")
        ttk.Button(barre, text="Sauvegarder et quitter",
                   command=self.sauvegarder_quitter).pack(side="left")
        ttk.Button(barre, text="Quitter", command=self.quitter).pack(side="left", padx=6)
        ttk.Button(barre, text="Validé…", command=self.valider).pack(side="right")

        ttk.Label(self, foreground="gray", padding=(8, 0), text=(
            "Ctrl+clic ou Shift+clic : sélection multiple · clic droit : Déplacer vers… · "
            "Ctrl+C / Ctrl+X / Ctrl+V · double-clic : ouvrir l'original")).pack(fill="x")

        corps = ttk.PanedWindow(self, orient="horizontal")
        corps.pack(fill="both", expand=True, padx=8, pady=6)

        gauche = ttk.Frame(corps)
        self.arbre = ttk.Treeview(gauche, show="tree", selectmode="browse")
        defil_g = ttk.Scrollbar(gauche, orient="vertical", command=self.arbre.yview)
        self.arbre.configure(yscrollcommand=defil_g.set)
        self.arbre.pack(side="left", fill="both", expand=True)
        defil_g.pack(side="right", fill="y")
        self.arbre.bind("<<TreeviewSelect>>", self._choisir_dossier)
        corps.add(gauche, weight=1)

        droite = ttk.Frame(corps)
        self.liste = ttk.Treeview(droite, show="tree", selectmode="extended")
        defil_d = ttk.Scrollbar(droite, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=defil_d.set)
        self.liste.pack(side="left", fill="both", expand=True)
        defil_d.pack(side="right", fill="y")
        self.liste.bind("<<TreeviewSelect>>", lambda e: self._maj_statut())
        self.liste.bind("<Double-1>", self._double_clic)
        self.liste.bind("<Button-3>", self._menu_contextuel)
        corps.add(droite, weight=4)

        self.statut = ttk.Label(self, padding=(8, 4), anchor="w")
        self.statut.pack(fill="x")

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Déplacer vers…", command=self.menu_deplacer)
        self.menu.add_separator()
        self.menu.add_command(label="Copier (Ctrl+C)", command=lambda: self.copier("copy"))
        self.menu.add_command(label="Couper (Ctrl+X)", command=lambda: self.copier("cut"))
        self.menu.add_command(label="Coller ici (Ctrl+V)", command=self.coller)
        self.menu.add_separator()
        self.menu.add_command(label="Ouvrir l'original", command=self.ouvrir_selection)

        self.bind("<Control-c>", lambda e: self.copier("copy"))
        self.bind("<Control-x>", lambda e: self.copier("cut"))
        self.bind("<Control-v>", lambda e: self.coller())
        self.bind("<Control-a>", lambda e: self.liste.selection_set(self.liste.get_children()))

    # --- Dossiers et affichage ---

    def _remplir_arbre(self):
        self.arbre.delete(*self.arbre.get_children())
        for rel in lister_dossiers():
            if rel == ".":
                self.arbre.insert("", "end", iid=".", open=True,
                                  text=f"Tri_Photos ({self.comptes.get(TRI, 0)})")
                continue
            d = TRI / rel
            parent = Path(rel).parent.as_posix()
            self.arbre.insert(parent, "end", iid=rel,
                              text=f"{d.name} ({self.comptes.get(d, 0)})")

    def _afficher_photos(self):
        for f in self.futurs:
            f.cancel()  # annule les miniatures du dossier précédent
        self.futurs = []
        self.generation += 1
        gen = self.generation
        self.miniatures = {}
        self.liste.delete(*self.liste.get_children())
        fichiers = photos_dans(self.dossier)
        for p in fichiers:
            self.liste.insert("", "end", iid=str(p), text=p.name)
        self._affiche = self.dossier
        for p in fichiers:
            fut = self.pool.submit(self._image_mini, p)
            fut.add_done_callback(lambda f, p=p, g=gen: self.file_mini.put((g, p, f)))
            self.futurs.append(fut)
        self._maj_statut()

    def _image_mini(self, p):
        """Exécuté en arrière-plan : retourne une image PIL (pas de PhotoImage ici)."""
        fichier = MINI / f"{cle_miniature(p)}.jpg"
        if not fichier.exists():
            generer_miniature(p).save(fichier, "JPEG", quality=80)
        with Image.open(fichier) as im:
            return im.convert("RGB")

    def _traiter_miniatures(self):
        """Dans la boucle principale : affiche les miniatures prêtes, par petits lots."""
        for _ in range(40):
            try:
                gen, p, fut = self.file_mini.get_nowait()
            except queue.Empty:
                break
            if gen != self.generation or not self.liste.exists(str(p)):
                continue
            try:
                photo = ImageTk.PhotoImage(fut.result())
            except Exception:
                continue
            self.miniatures[str(p)] = photo
            self.liste.item(str(p), image=photo)
        self.after(50, self._traiter_miniatures)

    
    def _choisir_dossier(self, _event=None):
        sel = self.arbre.selection()
        if not sel:
            return
        nouveau = TRI if sel[0] == "." else TRI / sel[0]
        if nouveau != self._affiche:
            self.dossier = nouveau
            self._afficher_photos()

    
    def _rafraichir(self):
        if not self.dossier.exists():
            self.dossier = TRI
        self._recompter()
        self._remplir_arbre()
        self._afficher_photos()
        rel = "." if self.dossier == TRI else self.dossier.relative_to(TRI).as_posix()
        if self.arbre.exists(rel):
            self.arbre.selection_set(rel)
            self.arbre.see(rel)

    def _maj_statut(self):
        n = len(self.liste.get_children())
        s = len(self.liste.selection())
        texte = f"{nom_dossier(self.dossier)} · {n} photo(s) · {s} sélectionnée(s)"
        if self.modifie:
            texte += "  ·  modifications non sauvegardées"
        self.statut.config(text=texte)

    # --- Actions sur les photos ---

    def _double_clic(self, event):
        ligne = self.liste.identify_row(event.y)
        if ligne:
            self.liste.selection_set(ligne)
            self.ouvrir_selection()

    def _menu_contextuel(self, event):
        ligne = self.liste.identify_row(event.y)
        if ligne and ligne not in self.liste.selection():
            self.liste.selection_set(ligne)
        if self.liste.selection():
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()

    def _memoriser(self, p, sha):
        st = p.stat()
        self.sha_par_chemin[str(p)] = (sha, st.st_size, st.st_mtime_ns)

    def _connu(self, p):
        info = self.sha_par_chemin.get(str(p))
        if not info:
            return False
        st = p.stat()
        return info[1] == st.st_size and info[2] == st.st_mtime_ns

    def _sha(self, p):
        if self._connu(p):
            return self.sha_par_chemin[str(p)][0]
        sha = empreinte(p)
        self._memoriser(p, sha)
        return sha

    def _recompter(self):
        self.comptes = Counter(p.parent for p in fichiers_tri())

    def ouvrir_selection(self):
        sel = self.liste.selection()
        if sel:
            self.ouvrir_original(Path(sel[0]))

    def ouvrir_original(self, copie):
        if self.index_dcim is None:
            self.statut.config(text="Indexation de DCIM…")
            self.update_idletasks()
            self.index_dcim = index_dcim()
        candidats = self.index_dcim.get(copie.stat().st_size, [])
        if candidats:
            sha = empreinte(copie)
            for c in candidats:
                if empreinte(c) == sha:
                    os.startfile(str(c))
                    self._maj_statut()
                    return
        messagebox.showinfo("Original introuvable",
                            "L'original de cette photo n'a pas été retrouvé dans DCIM.")
        self._maj_statut()

    def copier(self, mode):
        sel = self.liste.selection()
        if not sel:
            return
        self.presse = (mode, list(sel))
        action = "coupé(s)" if mode == "cut" else "copié(s)"
        self.statut.config(text=f"{len(sel)} élément(s) {action}. Ctrl+V pour coller ici.")

    def coller(self):
        if not self.presse:
            return
        mode, chemins = self.presse
        if mode == "cut":
            self.presse = None
            self.deplacer(chemins, self.dossier)
            return
        n = 0
        for c in chemins:
            src = Path(c)
            if src.exists():
                sha = self._sha(src)
                dest = unique(self.dossier / src.name)
                shutil.copy2(src, dest)
                self._memoriser(dest, sha)
                n += 1
        if n:
            self.modifie = True
        self._rafraichir()

    def deplacer(self, chemins, destination):
        destination.mkdir(parents=True, exist_ok=True)
        n = 0
        for c in chemins:
            src = Path(c)
            if not src.exists() or src.parent == destination:
                continue
            sha = self._sha(src)  # connu le plus souvent, donc instantané
            dest = unique(destination / src.name)
            shutil.move(str(src), str(dest))
            self.sha_par_chemin.pop(str(src), None)
            self._memoriser(dest, sha)
            n += 1
        if n:
            self.modifie = True
        self._rafraichir()

    def menu_deplacer(self):
        sel = self.liste.selection()
        if not sel:
            return
        choix = ChoixDossier(self, lister_dossiers())
        if choix.resultat is not None:
            cible = TRI if choix.resultat == "." else TRI / choix.resultat
            self.deplacer(sel, cible)

    # --- Sauvegarde, validation, fermeture ---

    def sauvegarder(self):
        """Enregistre où se trouve chaque photo dans le manifeste. Ne supprime rien."""
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            fichiers = fichiers_tri()
            inconnus = [p for p in fichiers if not self._connu(p)]
            # Seuls les fichiers nouveaux ou modifiés sont hachés, en parallèle
            with ThreadPoolExecutor(max_workers=8) as ex:
                for p, sha in zip(inconnus, ex.map(empreinte, inconnus)):
                    self._memoriser(p, sha)
            photos = {}
            for p in fichiers:
                sha, taille, _ = self.sha_par_chemin[str(p)]
                photos[sha] = {"fichier": p.relative_to(TRI).as_posix(),
                               "dossier": p.parent.relative_to(TRI).as_posix(),
                               "taille": taille}
            self.data["photos"] = photos
            sauver_manifeste(self.data, TRI, DCIM)
        except Exception as e:
            messagebox.showerror("Sauvegarde impossible", f"Erreur : {e}")
            return False
        finally:
            self.config(cursor="")
        self.modifie = False
        self._maj_statut()
        return True

    def sauvegarder_quitter(self):
        if self.sauvegarder():
            self.destroy()

    def quitter(self):
        if self.modifie:
            rep = messagebox.askyesnocancel(
                "Quitter",
                "Des changements ne sont pas enregistrés dans le manifeste.\n"
                "Sauvegarder avant de quitter ?")
            if rep is None:
                return
            if rep and not self.sauvegarder():
                return
        self.destroy()

    def valider(self):
        self.statut.config(text="Analyse de A_verifier…")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            dossier, copies, a_retirer, manquants = preparer_suppression()
        finally:
            self.config(cursor="")

        if not copies:
            if not messagebox.askyesno("Valider",
                                       "Il n'y a aucun fichier dans A_verifier. "
                                       "Enregistrer le classement comme validé ?"):
                self._maj_statut()
                return
        else:
            texte = (f"Cette action va envoyer à la Corbeille :\n"
                     f"  • {len(a_retirer)} original(aux) dans DCIM\n"
                     f"  • le dossier A_verifier ({len(copies)} fichier(s)) dans Tri_Photos\n\n"
                     "Les autres photos ne sont pas touchées. Tu peux restaurer "
                     "depuis la Corbeille.")
            if manquants:
                texte += (f"\n\n{manquants} copie(s) n'ont pas d'original retrouvé dans DCIM : "
                          "elles seront retirées de Tri_Photos sans toucher à DCIM.")
            if not messagebox.askyesno("Valider le tri", texte + "\n\nConfirmer ?",
                                       icon="warning"):
                self._maj_statut()
                return

        self.config(cursor="watch")
        self.update_idletasks()
        try:
            supprimer(dossier, a_retirer)
            self.data["validation"] = datetime.now().isoformat(timespec="seconds")
            self.modifie = True
            self.sauvegarder()
        except Exception as e:
            messagebox.showerror("Erreur", f"La suppression a été interrompue : {e}")
        finally:
            self.config(cursor="")
        self.index_dcim = None
        self._rafraichir()
        messagebox.showinfo("Validé", "Tri validé. Les fichiers supprimés sont dans la Corbeille.")


def main():
    if not TRI.is_dir():
        sys.exit("Tri_Photos est introuvable. Lance d'abord lancer.bat pour faire un tri.")
    Application().mainloop()


if __name__ == "__main__":
    main()