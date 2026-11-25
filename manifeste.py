#!/usr/bin/env python3
"""Manifeste : mémorise le cache des calculs et le classement (.manifeste.json)."""
import json
import os
import subprocess
from pathlib import Path

NOM = ".manifeste.json"
VERSION = 1


def _emplacements(racine_tri, dcim):
    return [Path(racine_tri) / NOM, Path(dcim) / NOM]


def vide():
    return {"version": VERSION, "labels": None, "cache": {}, "photos": {}}


def charger(racine_tri, dcim):
    """Lit le manifeste dans Tri_Photos, sinon dans DCIM, sinon crée un manifeste vide."""
    for p in _emplacements(racine_tri, dcim):
        if p.is_file():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                d.setdefault("labels", None)
                d.setdefault("cache", {})
                d.setdefault("photos", {})
                return d
            except (json.JSONDecodeError, OSError):
                print(f"Avertissement : {p} est illisible, il sera ignoré.")
    return vide()


def sauver(data, racine_tri, dcim):
    """Écrit le manifeste aux deux emplacements (écriture temporaire puis remplacement)."""
    racine_tri = Path(racine_tri)
    racine_tri.mkdir(parents=True, exist_ok=True)
    texte = json.dumps(data, ensure_ascii=False)
    for p in _emplacements(racine_tri, dcim):
        if not p.parent.is_dir():
            continue
        tmp = p.with_name(NOM + ".tmp")
        tmp.write_text(texte, encoding="utf-8")
        os.replace(tmp, p)
        _cacher(p)


def _cacher(p):
    if os.name == "nt":
        subprocess.run(["attrib", "+h", str(p)], check=False, capture_output=True)