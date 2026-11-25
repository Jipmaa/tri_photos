@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Reprendre le tri de photos

if not exist "Tri_Photos\" (
  echo Aucun dossier Tri_Photos trouve.
  echo Lance d'abord lancer.bat pour faire un premier tri.
  pause
  exit /b 1
)

if not exist "interface_tri.py" (
  echo L'interface n'est pas encore installee : interface_tri.py est absent.
  pause
  exit /b 1
)

rem Utilise l'environnement virtuel s'il existe, sinon le Python du systeme
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if exist "Tri_Photos\.manifeste.json" (
  echo Sauvegarde trouvee : le travail precedent va etre repris.
) else (
  echo Aucune sauvegarde trouvee : l'interface s'ouvrira sur le tri brut.
)

"%PY%" interface_tri.py
if errorlevel 1 (
  echo.
  echo L'interface s'est terminee avec une erreur. Lis le message ci-dessus.
  pause
)