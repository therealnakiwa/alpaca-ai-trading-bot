@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo Downloading ~10 years of daily prices for ~60 stocks and funds...
venv\Scripts\python download_daily.py --start 2016-01-01
pause
