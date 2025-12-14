@echo off
REM Setup script for Windows

echo Setting up environment...

REM Check if pyenv-win is installed
where pyenv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pyenv-win not found. Install from https://github.com/pyenv-win/pyenv-win
    exit /b 1
)

REM Install Python 3.11.0 if needed
for /f %%v in (.python-version) do set PYTHON_VERSION=%%v
pyenv install %PYTHON_VERSION% 2>nul
pyenv local %PYTHON_VERSION%

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate and install packages
echo Installing packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete!
echo.
echo To activate the environment:
echo   venv\Scripts\activate.bat

