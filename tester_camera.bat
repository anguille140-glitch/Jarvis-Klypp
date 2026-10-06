@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Mode camera seul : scan du visage puis controle a la main.
echo Ferme cette fenetre (ou Ctrl+C) pour arreter.
".venv\Scripts\python.exe" camera_mode.py
pause
