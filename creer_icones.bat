@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem recree les icones du bureau JARVIS / Eteindre JARVIS (sans fleche) et les touches Ctrl+Alt+J / Ctrl+Alt+Fin
".venv\Scripts\python.exe" creer_raccourcis.py
pause
