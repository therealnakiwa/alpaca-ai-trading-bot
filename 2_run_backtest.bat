@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
set /p SYM=Symbol to test [SPY]: 
if "%SYM%"=="" set SYM=SPY
venv\Scripts\python backtest.py --symbol %SYM% --days 60
pause
