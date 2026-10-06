@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem arrete le superviseur puis Jarvis (sans toucher a Chrome, Discord...)
powershell -NoProfile -Command "$f='%~dp0.cache\superviseur.json'; if(Test-Path $f){$j=Get-Content $f -Raw | ConvertFrom-Json; foreach($p in @($j.superviseur,$j.jarvis)){ if($p){ Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } }; Remove-Item $f -ErrorAction SilentlyContinue}"
if "%1"=="silencieux" exit /b 0
echo Jarvis est arrete (il redemarrera au prochain demarrage de Windows, sauf si tu lances retirer_demarrage.bat).
pause
