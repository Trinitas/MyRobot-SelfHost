@echo off
rem Starts myrobot_ai.py with Python 3.10-3.12. All settings are in myrobot_ai.py.
cd /d "%~dp0"
title MyRobot Local AI

set "PY="
if exist "data\.venv\Scripts\python.exe" set "PY=data\.venv\Scripts\python.exe"
for %%V in (3.12 3.11 3.10) do if not defined PY py -%%V --version >nul 2>&1 && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,12))" >nul 2>&1 && set "PY=python"

if not defined PY (
    echo.
    echo  No Python 3.10, 3.11 or 3.12 found.
    echo  Install Python 3.12 from https://www.python.org/downloads/
    echo.
    echo  Anaconda users: open Anaconda Prompt, activate an environment with
    echo  Python 3.10-3.12, go to this folder and run:  python myrobot_ai.py
    echo  ^(only needed once - after that START.bat works by itself^)
    echo.
    pause
    exit /b 1
)

%PY% myrobot_ai.py
pause
