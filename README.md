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

**Player Client (main player interface):**
```bash
python player/player_client.py
```

**Developer Client:**
```bash
python developer/developer_client.py
```

**Note:** There's also a legacy client in `client/client_gui.py` for reference, but the main player interface is `player/player_client.py`.

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
├── server/              # Server components
│   ├── db_server.py    # Database server (JSON file storage)
│   ├── lobby_server.py # Lobby server
│   ├── game_server.py  # Game server
│   ├── set_developer.py # Helper script to set user as developer
│   └── handlers/       # Request handlers
│       ├── auth_handler.py
│       ├── developer_handler.py
│       └── game_handler.py
├── client/              # Legacy client GUI (older implementation)
│   ├── client_gui.py
│   ├── records_screen.py
│   ├── store_screen.py
│   └── shared.py
├── player/              # Player client (main player interface)
│   ├── player_client.py
│   └── downloads/       # Player-downloaded games (per-user folders)
├── developer/           # Developer client
│   ├── dev_client.py
│   └── games/          # Developer's local games
├── gui/                 # Shared GUI base classes
│   └── base_gui.py
├── common/              # Shared code
│   ├── config.py       # Configuration
│   ├── db_operations.py # Database operations (JSON storage)
│   ├── db_schema.py    # Database schema initialization
│   ├── protocol.py     # Network protocol
│   ├── password_utils.py
│   └── game_rules.py
├── assets/              # Assets (fonts, etc.)
│   └── fonts/
├── storage/             # JSON data files (created at runtime)
│   ├── users.json
│   ├── games.json
│   ├── game_versions.json
│   └── game_logs.json
├── venv/                # Virtual environment (created by setup)
├── create_test_users.py # Script to create test users
├── reset_sessions.py    # Helper script
├── setup.sh             # Setup script (Linux/macOS)
├── setup.bat            # Setup script (Windows)
├── requirements.txt     # Python dependencies
└── README.md
```
