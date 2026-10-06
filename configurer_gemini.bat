@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Le cerveau de Jarvis est Gemini (IA gratuite de Google).
echo 1. Va sur https://aistudio.google.com/apikey et connecte-toi avec un compte Google
echo 2. Clique sur "Create API key" puis copie la cle
echo.
start "" "https://aistudio.google.com/apikey"
echo Colle ta cle Gemini (clic droit pour coller) puis Entree :
set /p GKEY=
if exist .env (
  findstr /v /b /c:"GEMINI_API_KEY=" .env > .env.tmp
  move /y .env.tmp .env >nul
)
>> .env echo GEMINI_API_KEY=%GKEY%
echo.
echo Cle Gemini enregistree. Tu peux tester avec parler_a_jarvis.bat
pause
