@echo off
cd /d "%~dp0"
call _find_python.bat || exit /b 1
echo Creating virtual environment...
if not exist venv "%PY%" -m venv venv
echo Installing packages...
venv\Scripts\python -m pip install --upgrade pip -q
venv\Scripts\python -m pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
echo.
echo Setup done. Notepad will open your .env file:
echo Paste your PAPER API Key ID and Secret Key, then save and close it.
notepad .env
pause
