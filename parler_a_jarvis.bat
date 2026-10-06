@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Assistant vocal seul (sans le reveil au clap).
echo Dis "Jarvis" suivi de ta demande, par exemple : "Jarvis, ouvre Discord".
echo Pour voir ce que Jarvis entend : mets JARVIS_DEBUG=1 (ou lance parler_a_jarvis_debug.bat)
".venv\Scripts\python.exe" jarvis.py --assistant
pause
