# Tri de photos

> **Projet vibe codé.** Ce programme a été écrit avec l'aide d'une IA, en itérant pas à pas. Il n'a pas été testé sur toutes les configurations possibles. Son but n'est **pas** d'automatiser le tri à 100 %, mais de **simplifier la tâche** : il range, regroupe et signale, et c'est toi qui décides au final de ce qui est gardé ou supprimé. Seul le README.md a été relu entièrement.

## Ce que fait le programme

- Repère les **doublons exacts** et les **quasi-doublons** (photos très proches), et garde la meilleure version.
- Sort les photos **sombres**, les **captures d'écran** et les images **sans intérêt** (tableaux, feuilles, etc.) dans un dossier à vérifier.
- Range les photos par **lieu de vie** (Avaux, Reims, Belfort, Tanlay… ceux que tu configures).
- Crée un dossier par **voyage**, à partir des photos géolocalisées loin de tes lieux de vie.
- Le reste va dans `Autres`, les WhatsApp dans `WhatsApp`.

Le programme **ne supprime jamais rien**. Il copie les photos dans un nouveau dossier, et tes originaux restent intacts.

## Ce qu'il te faut

- Un ordinateur **Windows 11**.
- Une copie de tes photos dans un dossier nommé **`DCIM`** (voir l'étape 2).
- Une connexion Internet pour la première installation, et pour rechercher tes lieux de vie.
- Environ **5 Go** de libre sur le disque (installation de l'IA et des bibliothèques).
- Une carte graphique NVIDIA est **recommandée** mais pas obligatoire : sans elle, le programme fonctionne, plus lentement.

## Mode d'emploi

### Étape 1 : télécharger le projet

Sur la page GitHub du projet, clique sur **Code**, puis **Download ZIP**. Fais un clic droit sur le fichier ZIP téléchargé, puis **Extraire tout**. Ouvre le dossier extrait.

### Étape 2 : copier tes photos

Connecte ton téléphone à l'ordinateur par câble USB, puis :

1. Ouvre l'**Explorateur de fichiers** et repère ton téléphone (dans « Ce PC »).
2. Ouvre le dossier **DCIM** du téléphone, puis copie **tout son contenu** dans le dossier du projet, en créant un dossier nommé **`DCIM`**.

**__ATTENTION__** Les photos WhatsApp se trouvent dans `/Internal storage/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images` (ou `WhatsApp Videos`). Il est donc recommandé de copier également ces dossiers dans le dossier DCIM sur l'ordinateur.
Le résultat doit ressembler à ceci :

```
Dossier du projet\
├── DCIM\            ← tes photos copiées ici
├── lancer.bat
├── lancer.ps1
├── lieux_de_vie.py
└── tri_photos.py
```

> Le dossier doit s'appeler exactement `DCIM` et se trouver **à côté** de `lancer.bat`. Sinon le programme s'arrête avec un message d'erreur.

### Étape 3 : lancer le programme

**Double-clique sur `lancer.bat`.**

Une fenêtre noire s'ouvre. Suis les questions à l'écran :

1. **« Créer un environnement virtuel ? [O/n] »** : tape `O` puis Entrée. C'est recommandé, il isole le programme du reste de ton ordinateur.
2. **Installation** : la première fois, elle prend du temps (plusieurs Go à télécharger, souvent 15 à 30 minutes). Ne ferme pas la fenêtre. Si Python n'est pas installé, il l'est automatiquement.
3. **Lieux de vie** : une fenêtre s'ouvre. Tape le nom d'une ville (par exemple « Lyon »), clique sur **Rechercher**, sélectionne le bon résultat, donne-lui un nom, puis clique sur **Ajouter ce lieu**. Recommence pour chaque lieu où tu as vécu pour que ce lieu ne soit pas considéré comme un "voyage". Quand c'est fini, clique sur **Enregistrer et fermer**.
4. **Tri** : le programme analyse tes photos. Cela peut prendre de quelques minutes à plusieurs heures selon le nombre de photos.

Quand tout est terminé, la fenêtre affiche un message. Appuie sur Entrée pour la fermer.

### Étape 4 : regarder le résultat

Un dossier **`Tri_Photos`** apparaît à côté de `lancer.bat`. Ouvre-le :

| Dossier | Contenu |
|---|---|
| `Belfort`, `Reims`, … | Photos prises dans tes lieux de vie |
| `Voyages` | Un sous-dossier par voyage |
| `Autres` | Les photos sans catégorie précise |
| `WhatsApp` | Les images WhatsApp |
| `Captures` | Captures d'écran |
| `Snapchat_Clipped` | Photos Snapchat et Clipped |
| `Inconnu` | Fichiers sans aucune date ni position |
| `A_verifier` | À contrôler à la main : doublons, photos sombres, inutiles |
| `rapport_doublons.html` | Page à ouvrir dans un navigateur pour comparer les doublons |

Dans chaque dossier de photos gardées, un fichier **`A_NE_PAS_SUPPRIMER.txt`** indique la meilleure version et les doublons associés.

## Conseils importants

- **Vérifie avant de supprimer.** Le programme se trompe parfois : une photo utile peut finir dans `inutiles` ou `trop_sombres`.
- **Ne supprime rien sur ton téléphone** tant que tu n'as pas vérifié le résultat.
- **Commence par un petit test** : copie quelques centaines de photos dans `DCIM` et lance le programme dessus.
- **En cas de problème**, ferme la fenêtre, relis le message d'erreur affiché, puis relance `lancer.bat`.

## Lancer le programme en simulation

Pour voir ce qui serait fait sans rien copier, ouvre PowerShell dans le dossier du projet et tape :

```powershell
python .\tri_photos.py --simuler
```

## Dépannage

| Problème | Solution |
|---|---|
| « Le dossier DCIM est introuvable » | Vérifie que le dossier s'appelle `DCIM` et qu'il est à côté de `lancer.bat`. |
| Windows bloque le fichier | Clique sur « Informations complémentaires », puis « Exécuter quand même ». |
| Le programme est très lent | C'est normal sans carte NVIDIA. Laisse-le tourner. |
| Erreur lors de la recherche de lieu | Vérifie ta connexion Internet, puis réessaie. |

## Licence et confidentialité

Le programme fonctionne **hors ligne** pour le tri. Tes photos ne quittent pas ton ordinateur. Seule la recherche de lieux utilise Internet, via OpenStreetMap (Nominatim).
