@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
venv\Scripts\python -m pip install -r requirements.txt -q
echo.
echo STEP 1: store your Alpaca keys in Windows Credential Manager (typing is hidden)
venv\Scripts\python security.py --set-keys
echo.
echo STEP 2: approve the current code so tampering can be detected
venv\Scripts\python security.py --approve
echo.
echo Done. You can now delete the two key lines from .env.
pause
