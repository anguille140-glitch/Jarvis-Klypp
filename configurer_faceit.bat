@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Colle ta cle API FACEIT (clic droit pour coller) puis Entree :
set /p FKEY=
if exist .env (
  findstr /v /b /c:"FACEIT_API_KEY=" .env > .env.tmp
  move /y .env.tmp .env >nul
)
>> .env echo FACEIT_API_KEY=%FKEY%
echo.
echo Cle FACEIT enregistree dans .env. Relance Jarvis pour voir ton elo.
pause
