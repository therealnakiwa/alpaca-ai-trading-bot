@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo Downloading 1 year of news headlines for the stocks in the data folder...
venv\Scripts\python download_news.py --days 365
pause
