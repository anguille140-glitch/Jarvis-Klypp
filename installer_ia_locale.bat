@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lance d'abord installer.bat
  pause
  exit /b 1
)
echo Installation de l'IA locale de Jarvis (gratuite, sur ton PC).
echo Ca telecharge environ 10 a 12 Go la premiere fois : laisse tourner.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements-ia-locale.txt
if errorlevel 1 (
  echo Une erreur est survenue pendant l'installation des modules. Fais une capture de cette fenetre.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" installer_ia_locale.py
pause
