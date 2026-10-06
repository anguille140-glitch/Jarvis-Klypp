@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Colle ta cle ElevenLabs (clic droit pour coller) puis Entree :
set /p KEY=
echo Colle ton Voice ID puis Entree :
set /p VID=
if exist .env (
  findstr /v /b /c:"ELEVENLABS_API_KEY=" /c:"ELEVENLABS_VOICE_ID=" .env > .env.tmp
  move /y .env.tmp .env >nul
)
>> .env echo ELEVENLABS_API_KEY=%KEY%
>> .env echo ELEVENLABS_VOICE_ID=%VID%
echo.
echo Voix enregistree dans .env. Tu peux fermer cette fenetre.
pause
