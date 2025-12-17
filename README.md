# Network Programming HW3

Multi-game platform with developer tools.

## Setup

**Requirements:** Python 3.11+ (system-wide) OR pyenv installed

**Linux/macOS:**
```bash
./setup.sh
source venv/bin/activate
```

**Windows:**
```cmd
setup.bat
venv\Scripts\activate.bat
```

This will:
1. Use system Python 3.11+ if available (fast), otherwise install via pyenv (only if not already installed)
2. Create virtual environment (`venv/`) (skips if already exists)
3. Install packages from `requirements.txt`

**Performance:** 
- **First run:** If using pyenv, Python installation may take 10-20 minutes (one-time)
- **Subsequent runs:** Script detects existing Python/venv and skips installation (seconds)
- **Fast path:** If you have Python 3.11+ system-wide, the script will use it automatically (no pyenv needed)

**Storage:** This project uses JSON file storage (no SQLite database required). Data files are automatically created in the `storage/` directory.

## Running

**Important:** Always run commands from the project root directory.

**Activate environment first:**
```bash
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate.bat  # Windows
```

**Start servers (in order):**
```bash
# Terminal 1: Database server (must be running first)
python server/db_server.py

# Terminal 2: Lobby server (connects to database server)
python server/lobby_server.py
```

**Then start clients:**

**Client:**
```bash
python client/client_gui.py
```

**Developer:**
```bash
python developer/developer_client.py
```

**Create test users:**
```bash
python create_test_users.py
```
This creates:
- `alice` / `alice123` (developer)
- `bob` / `bob123` (regular user)
- `dev` / `dev123` (developer)
- `user` / `user123` (regular user)

**Set existing user as developer:**
```bash
python server/set_developer.py <username>
```

## Project Structure

```
NPHW3/
├── server/          # Server components
├── client/          # Client GUI
├── developer/       # Developer client
├── common/          # Shared code
├── venv/            # Virtual environment (created by setup)
└── requirements.txt # Python packages
```
