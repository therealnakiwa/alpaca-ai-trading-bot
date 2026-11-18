@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo Starting the bot. Close this window or press Ctrl+C to stop it.
echo To flatten all positions and stop, double-click 4_KILL_SWITCH.bat
echo.
venv\Scripts\python bot.py
pause
