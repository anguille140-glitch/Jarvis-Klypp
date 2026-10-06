@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "jarvis.log" (
  echo Pas encore de journal : lance Jarvis une fois, puis recommence.
  pause
  exit /b 1
)
rem les 80 dernieres lignes du journal -> derniers_logs.txt + copiees (Ctrl+V pour les coller a Claude)
powershell -NoProfile -Command "$l = Get-Content -Path 'jarvis.log' -Tail 80 -Encoding UTF8; $l | Set-Content -Path 'derniers_logs.txt' -Encoding UTF8; $l | Set-Clipboard"
start notepad "derniers_logs.txt"
echo.
echo Les dernieres lignes du journal sont COPIEES : colle-les simplement dans la conversation avec Claude (Ctrl+V).
echo Elles sont aussi dans le fichier derniers_logs.txt (ouvert dans le Bloc-notes).
pause
