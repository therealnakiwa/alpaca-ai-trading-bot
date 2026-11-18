@echo off
cd /d "%~dp0"
echo stop> STOP
echo Kill switch set. The bot will close all positions and exit within about a minute.
echo Delete the file named STOP before running the bot again.
pause
