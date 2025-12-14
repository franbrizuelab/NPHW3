#!/bin/bash
# Setup script: Creates virtual environment and installs packages

set -e

echo "Setting up environment..."

# Check pyenv
if ! command -v pyenv &> /dev/null; then
    echo "ERROR: pyenv not found. Install it first: curl https://pyenv.run | bash"
    exit 1
fi

# Install Python 3.11.0 if needed
PYTHON_VERSION=$(cat .python-version)
if ! pyenv versions --bare | grep -q "^$PYTHON_VERSION$"; then
    echo "Installing Python $PYTHON_VERSION (this may take 10-20 minutes)..."
    pyenv install $PYTHON_VERSION
fi

# Set local Python version
pyenv local $PYTHON_VERSION

#" Create virtual environment
echo "Creating virtual environment..."
python -m venv venv

# Activate and install packages
echo "Installing packages..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

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
