@echo off
chcp 65001 >nul
call "%~dp0arreter_jarvis.bat" silencieux
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk" 2>nul
echo Jarvis est arrete et ne demarrera plus tout seul avec Windows.
pause
