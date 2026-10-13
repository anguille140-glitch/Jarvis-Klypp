@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Lance d'abord installer.bat
  pause
  exit /b 1
)
rem arrete l'ancien Jarvis cache s'il tourne
call "%~dp0arreter_jarvis.bat" silencieux
rem demarrage automatique : le superviseur (cache) lance Jarvis et le relance s'il s'arrete
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortCut([Environment]::GetFolderPath('Startup')+'\Jarvis.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='superviseur.py --demarrage'; $s.WorkingDirectory='%~dp0'; $s.Save()"
if errorlevel 1 (
  echo Une erreur est survenue. Fais une capture de cette fenetre.
  pause
  exit /b 1
)
rem icones du bureau : JARVIS (Ctrl+Alt+J) et Eteindre JARVIS (Ctrl+Alt+Fin)
".venv\Scripts\python.exe" creer_raccourcis.py
start "" ".venv\Scripts\pythonw.exe" superviseur.py
echo.
echo C'est fait :
echo  - Jarvis tourne maintenant en arriere-plan, sans fenetre. Dis "salut Jarvis" (ou "bonjour Jarvis", "Jarvis reveille-toi"...),
echo    tape deux fois dans tes mains, double-clique l'icone JARVIS du bureau ou fais Ctrl+Alt+J.
echo  - Pour l'eteindre : "Jarvis, fin de programme" / "au revoir Jarvis", l'icone Eteindre JARVIS ou Ctrl+Alt+Fin.
echo  - Il se lancera tout seul a chaque demarrage de Windows.
echo  - S'il plante ou perd le micro, il redemarre tout seul.
echo  - Journal : jarvis.log    Arret : arreter_jarvis.bat    Retirer : retirer_demarrage.bat
pause
