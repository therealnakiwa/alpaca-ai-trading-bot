@echo off
rem Finds a Python to use: Anaconda first, then whatever is on PATH.
set "PY="
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Could not find Python. Install Anaconda or Python 3 and try again.
  pause
  exit /b 1
)
