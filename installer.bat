@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
py -3 -c "" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python -c "" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython
echo Creation de l'environnement...
%PY% -m venv .venv
if errorlevel 1 goto fail
echo Installation des composants, patiente un peu...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist "modeles\vosk-fr" (
  echo Telechargement de la reconnaissance du mot "Jarvis" ^(40 Mo^)...
  if not exist "modeles" mkdir "modeles"
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip' -OutFile 'modeles\vosk.zip'; Expand-Archive 'modeles\vosk.zip' 'modeles' -Force; Rename-Item 'modeles\vosk-model-small-fr-0.22' 'vosk-fr'; Remove-Item 'modeles\vosk.zip'"
  if not exist "modeles\vosk-fr" goto fail
)
echo.
echo Installation terminee.
echo Si ce n'est pas deja fait : configurer_voix.bat puis configurer_gemini.bat
pause
exit /b 0
:nopython
echo Python n'est pas installe. Installe-le depuis https://www.python.org/downloads/
echo et coche la case "Add Python to PATH", puis relance ce fichier.
pause
exit /b 1
:fail
echo Une erreur est survenue. Fais une capture de cette fenetre et envoie-moi la.
pause
exit /b 1
