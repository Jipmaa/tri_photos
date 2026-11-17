#!/usr/bin/env python3
"""Fenêtre de configuration des lieux de vie (enregistrés dans lieux.json)."""
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONFIG = Path(__file__).with_name("lieux.json")
RAYON_DEFAUT = 50


def rechercher_lieu(texte):
    """Recherche une ville ou une adresse via Nominatim (OpenStreetMap, sans clé)."""
    url = "https://nominatim.openstreetmap.org/search?" + urlencode(
        {"q": texte, "format": "json", "limit": 8, "accept-language": "fr"})
    req = Request(url, headers={"User-Agent": "TriPhotos/1.0 (usage personnel)"})
    with urlopen(req, timeout=15) as rep:
        return json.loads(rep.read().decode("utf-8"))


def charger():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"rayon_km": RAYON_DEFAUT, "lieux": []}


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lieux de vie")
        self.geometry("640x560")
        self.donnees = charger()
        self.resultats = []
        self._construire()
        self._rafraichir_lieux()

    def _construire(self):
        cadre = ttk.Frame(self, padding=12)
        cadre.pack(fill="both", expand=True)

        ttk.Label(cadre, text="1. Recherche une ville ou une adresse :").pack(anchor="w")
        ligne = ttk.Frame(cadre)
        ligne.pack(fill="x", pady=4)
        self.saisie = ttk.Entry(ligne)
        self.saisie.pack(side="left", fill="x", expand=True)
        self.saisie.bind("<Return>", lambda e: self.chercher())
        ttk.Button(ligne, text="Rechercher", command=self.chercher).pack(side="left", padx=6)

        self.liste_res = tk.Listbox(cadre, height=6)
        self.liste_res.pack(fill="x")
        self.liste_res.bind("<<ListboxSelect>>", self.selection_resultat)

        ttk.Label(cadre, text="2. Nom du lieu (utilisé pour les dossiers) :").pack(
            anchor="w", pady=(10, 0))
        self.nom = ttk.Entry(cadre)
        self.nom.pack(fill="x", pady=4)

        ligne2 = ttk.Frame(cadre)
        ligne2.pack(fill="x")
        ttk.Label(ligne2, text="Rayon autour du lieu (km) :").pack(side="left")
        self.rayon = tk.StringVar(value=str(self.donnees.get("rayon_km", RAYON_DEFAUT)))
        ttk.Spinbox(ligne2, from_=5, to=500, increment=5, width=6,
                    textvariable=self.rayon).pack(side="left", padx=6)
        ttk.Button(ligne2, text="Ajouter ce lieu", command=self.ajouter).pack(side="right")

        ttk.Label(cadre, text="3. Lieux de vie enregistrés :").pack(anchor="w", pady=(10, 0))
        self.liste_lieux = tk.Listbox(cadre, height=8)
        self.liste_lieux.pack(fill="both", expand=True)
        ttk.Button(cadre, text="Supprimer le lieu sélectionné",
                   command=self.supprimer).pack(anchor="w", pady=4)

        self.statut = ttk.Label(cadre, text="", foreground="gray")
        self.statut.pack(anchor="w")
        ttk.Button(cadre, text="Enregistrer et fermer",
                   command=self.enregistrer).pack(side="right", pady=6)

    def chercher(self):
        texte = self.saisie.get().strip()
        if not texte:
            return
        self.statut.config(text="Recherche en cours...")
        self.update_idletasks()
        try:
            self.resultats = rechercher_lieu(texte)
        except Exception as e:
            self.statut.config(text=f"Erreur de recherche (vérifie ta connexion) : {e}")
            return
        self.liste_res.delete(0, "end")
        for r in self.resultats:
            self.liste_res.insert("end", r["display_name"])
        self.statut.config(text=f"{len(self.resultats)} résultat(s)"
                           if self.resultats else "Aucun résultat")

    def selection_resultat(self, _event):
        sel = self.liste_res.curselection()
        if sel:
            premier = self.resultats[sel[0]]["display_name"].split(",")[0].strip()
            self.nom.delete(0, "end")
            self.nom.insert(0, premier)

    def ajouter(self):
        sel = self.liste_res.curselection()
        if not sel:
            messagebox.showwarning("Attention", "Sélectionne d'abord un résultat.")
            return
        nom = self.nom.get().strip()
        if not nom:
            messagebox.showwarning("Attention", "Donne un nom au lieu.")
            return
        try:
            rayon = int(self.rayon.get())
        except ValueError:
            messagebox.showwarning("Attention", "Le rayon doit être un nombre entier.")
            return
        r = self.resultats[sel[0]]
        self.donnees["lieux"].append({"nom": nom, "lat": float(r["lat"]), "lon": float(r["lon"])})
        self.donnees["rayon_km"] = rayon
        self._rafraichir_lieux()
        self.statut.config(text=f"« {nom} » ajouté.")

    def supprimer(self):
        sel = self.liste_lieux.curselection()
        if sel:
            del self.donnees["lieux"][sel[0]]
            self._rafraichir_lieux()

    def _rafraichir_lieux(self):
        self.liste_lieux.delete(0, "end")
        for l in self.donnees["lieux"]:
            self.liste_lieux.insert("end", f"{l['nom']}  ({l['lat']:.3f}, {l['lon']:.3f})")

    def enregistrer(self):
        if not self.donnees["lieux"]:
            if not messagebox.askyesno("Aucun lieu",
                                       "Aucun lieu de vie n'est enregistré. Continuer quand même ?"):
                return
        CONFIG.write_text(json.dumps(self.donnees, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        self.destroy()


def main():
    Application().mainloop()


if __name__ == "__main__":
    main()