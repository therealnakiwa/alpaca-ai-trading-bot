@echo off
cd /d "%~dp0"
if not exist venv ( echo Run 1_setup.bat first. & pause & exit /b 1 )
echo == Audit log tamper check ==
venv\Scripts\python security.py --verify-audit
echo.
echo == Secret scan (run before every GitHub push) ==
venv\Scripts\python scan_secrets.py
echo.
echo == Security test suite ==
venv\Scripts\python -m pytest -q
pause
