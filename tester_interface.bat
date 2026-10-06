@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Test de l'interface seule (aucun clap, aucune application ouverte)...
".venv\Scripts\python.exe" jarvis.py --demo
echo.
echo Si une erreur est affichee ci-dessus, fais une capture et envoie-la moi.
pause
