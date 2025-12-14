# Network Programming HW3

Multi-game platform with developer tools.

## Setup

**Requirements:** pyenv installed

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
1. Install Python 3.11.0 via pyenv
2. Create virtual environment (`venv/`)
3. Install packages from `requirements.txt`

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
