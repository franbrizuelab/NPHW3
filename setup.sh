#!/bin/bash
# Setup script: Creates virtual environment and installs packages
# Storage: Uses JSON file storage (no SQLite database required)

set -e

echo "Setting up environment..."

# Check if system Python 3.11+ is available (faster alternative)
if command -v python3 &> /dev/null; then
    # Compare version (requires 3.11+)
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        SYSTEM_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        echo "Using system Python $SYSTEM_VERSION (faster than pyenv installation)"
        USE_SYSTEM_PYTHON=true
    else
        USE_SYSTEM_PYTHON=false
    fi
else
    USE_SYSTEM_PYTHON=false
fi

# If system Python not available, use pyenv
if [ "$USE_SYSTEM_PYTHON" = false ]; then
    # Check pyenv
    if ! command -v pyenv &> /dev/null; then
        echo "ERROR: pyenv not found and no suitable system Python detected."
        echo "Install pyenv: curl https://pyenv.run | bash"
        echo "Or install Python 3.11+ system-wide and run this script again"
        exit 1
    fi
    
    # Install Python 3.11.0 if needed (only if not already installed)
    PYTHON_VERSION=$(cat .python-version)
    # Faster check: use pyenv versions with quiet flag
    if ! pyenv versions --bare 2>/dev/null | grep -q "^$PYTHON_VERSION$"; then
        echo "Installing Python $PYTHON_VERSION via pyenv (this may take 10-20 minutes)..."
        echo "Tip: If you have Python 3.11+ system-wide, the script will detect and use it automatically"
        pyenv install $PYTHON_VERSION
    else
        echo "Python $PYTHON_VERSION already installed via pyenv, skipping..."
    fi
    
    # Set local Python version
    pyenv local $PYTHON_VERSION
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Create virtual environment only if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
else
    echo "Virtual environment already exists, skipping creation..."
fi

# Activate and install/upgrade packages
echo "Installing/upgrading packages..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo ""
echo "Setup complete!"
echo ""
echo "To activate the environment:"
echo "  source venv/bin/activate"
echo ""
echo "Then run:"
echo "  Server: python server/db_server.py"
echo "  Client: python client/client_gui.py"
echo "  Developer: python developer/developer_client.py"
