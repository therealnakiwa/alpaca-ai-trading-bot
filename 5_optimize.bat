@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo Tests 3 strategies (~400 setting combos) on older data, then checks the best ones on newer data.
set /p SYMS=Symbols separated by spaces [SPY QQQ AAPL TSLA NVDA]: 
if "%SYMS%"=="" set SYMS=SPY QQQ AAPL TSLA NVDA
venv\Scripts\python optimize.py --symbols %SYMS% --days 120
pause
