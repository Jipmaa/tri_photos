# lancer.ps1 : installe ce qu'il faut, configure les lieux de vie et lance le tri
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Pause-Fin {
    Read-Host "`nAppuie sur Entrée pour quitter" | Out-Null
}

function Rafraichir-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

function Trouver-Python {
    # Le « python » du Microsoft Store n'est qu'un raccourci : on vérifie la vraie version 3
    $candidats = @("python", "py") | ForEach-Object {
        Get-Command $_ -ErrorAction SilentlyContinue
    } | Where-Object { $_ } | ForEach-Object { $_.Source }
    $candidats += "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    foreach ($chemin in $candidats) {
        if ($chemin -and (Test-Path $chemin)) {
            $v = & $chemin -c "import sys; print(sys.version_info[0])" 2>$null
            if ($v -eq "3") { return $chemin }
        }
    }
    return $null
}

function Installer-Python {
    Write-Host "Python 3 introuvable. Installation via winget..." -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget est absent. Installe Python 3.12 depuis https://www.python.org/downloads/ " +
              "(coche « Add python.exe to PATH »), puis relance ce script."
    }
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    Rafraichir-Path
    $p = Trouver-Python
    if (-not $p) {
        throw "Python est installé mais introuvable. Ferme cette fenêtre, rouvre PowerShell et relance le script."
    }
    return $p
}

function Installer-Dependances($py) {
    Write-Host "`nInstallation des dépendances (la première fois, plusieurs Go)..." -ForegroundColor Cyan
    & $py -m pip install --upgrade pip
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        Write-Host "Carte NVIDIA détectée : PyTorch avec CUDA."
        & $py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    } else {
        Write-Host "Pas de carte NVIDIA détectée : PyTorch version CPU."
        & $py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    }
    if ($LASTEXITCODE -ne 0) { throw "Échec de l'installation de PyTorch." }

    & $py -m pip install pillow pillow-heif imagehash opencv-python reverse_geocoder numpy open_clip_torch send2trash
    if ($LASTEXITCODE -ne 0) { throw "Échec de l'installation des dépendances." }

    New-Item -ItemType File -Force (Join-Path $PSScriptRoot ".deps_ok") | Out-Null
}

try {
    Write-Host "=== Tri de photos ===" -ForegroundColor Cyan

    # 1. DCIM doit être à côté du script
    $dcim = Join-Path $PSScriptRoot "DCIM"
    if (-not (Test-Path -LiteralPath $dcim -PathType Container)) {
        Write-Host "ERREUR : le dossier DCIM est introuvable." -ForegroundColor Red
        Write-Host "Place le dossier DCIM ici : $PSScriptRoot"
        Pause-Fin
        exit 1
    }

    # 2. Environnement virtuel ?
    $reponse = Read-Host "Créer un environnement virtuel (recommandé) ? [O/n]"
    $venv = ($reponse -eq "") -or ($reponse -match "^[oOyY]")

    # 3. Python
    $python = Trouver-Python
    if (-not $python) { $python = Installer-Python }
    Write-Host "Python utilisé : $python"

    if ($venv) {
        $venvDir = Join-Path $PSScriptRoot ".venv"
        if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
            Write-Host "Création de l'environnement virtuel..." -ForegroundColor Cyan
            & $python -m venv $venvDir
        }
        . (Join-Path $venvDir "Scripts\Activate.ps1")
        $py = Join-Path $venvDir "Scripts\python.exe"
        Write-Host "Environnement virtuel activé."
    } else {
        $py = $python
    }

    # 4. Dépendances (une seule fois, sauf si tu supprimes .deps_ok)
    if (-not (Test-Path (Join-Path $PSScriptRoot ".deps_ok"))) {
        Installer-Dependances $py
    }

    # 4bis. send2trash est nécessaire à l'interface (installation ajoutée après coup)
    $ancien = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $py -c "import send2trash" *> $null
    $manque = $LASTEXITCODE -ne 0
    $ErrorActionPreference = $ancien
    if ($manque) {
        Write-Host "Installation de send2trash..." -ForegroundColor Cyan
        & $py -m pip install send2trash
    }

    # 5. Lieux de vie
    $lieux = Join-Path $PSScriptRoot "lieux.json"
    if (-not (Test-Path $lieux)) {
        Write-Host "`nConfiguration des lieux de vie..." -ForegroundColor Cyan
        & $py (Join-Path $PSScriptRoot "lieux_de_vie.py")
    } else {
        $modif = Read-Host "`nModifier les lieux de vie enregistrés ? [o/N]"
        if ($modif -match "^[oOyY]") { & $py (Join-Path $PSScriptRoot "lieux_de_vie.py") }
    }

    # 6. Tri
    Write-Host "`nLancement du tri..." -ForegroundColor Cyan
    & $py (Join-Path $PSScriptRoot "tri_photos.py") "DCIM" "Tri_Photos"

    # 7. Interface de révision
    if (Test-Path (Join-Path $PSScriptRoot "Tri_Photos")) {
        $rep = Read-Host "`nOuvrir l'interface de révision maintenant ? [O/n]"
        if ($rep -eq "" -or $rep -match "^[oOyY]") {
            & $py (Join-Path $PSScriptRoot "interface_tri.py")
        }
    }
}
catch {
    Write-Host "`nERREUR : $($_.Exception.Message)" -ForegroundColor Red
}
Pause-Fin