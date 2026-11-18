@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo Downloading 1 year of 5-minute price data for 20 stocks. Takes a few minutes...
venv\Scripts\python download_data.py --days 365
pause
