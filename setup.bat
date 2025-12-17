@echo off
REM Setup script for Windows
REM Storage: Uses JSON file storage (no SQLite database required)

echo Setting up environment...

REM Check if pyenv-win is installed
where pyenv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pyenv-win not found. Install from https://github.com/pyenv-win/pyenv-win
    exit /b 1
)

REM Install Python 3.11.0 if needed (only if not already installed)
for /f %%v in (.python-version) do set PYTHON_VERSION=%%v
pyenv versions | findstr /C:"%PYTHON_VERSION%" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing Python %PYTHON_VERSION% (this may take 10-20 minutes)...
    pyenv install %PYTHON_VERSION%
) else (
    echo Python %PYTHON_VERSION% already installed, skipping...
)
pyenv local %PYTHON_VERSION%

REM Create virtual environment only if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists, skipping creation...
)

REM Activate and install/upgrade packages
echo Installing/upgrading packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo.
echo Setup complete!
echo.
echo To activate the environment:
echo   venv\Scripts\activate.bat

