# Database schema definitions and migration utilities
# SQLite database schema for the game platform

import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

# Database file path
DB_FILE = os.path.join('storage', 'database.db')

def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0

def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set the schema version in the database."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()

def create_tables(conn: sqlite3.Connection):
    """Create all database tables."""
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT DEFAULT 'offline',
            is_developer BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            author TEXT NOT NULL,
            description TEXT,
            current_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (author) REFERENCES users(username)
        )
    """)
    
    # Game Versions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_hash TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES games(id),
            UNIQUE(game_id, version)
        )
    """)
    
    # Game Logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matchid TEXT UNIQUE NOT NULL,
            game_id INTEGER,
            users TEXT NOT NULL,
            results TEXT NOT NULL,
            winner TEXT,
            reason TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    """)
    
    conn.commit()
    logger.info("Database tables created successfully")

def initialize_database():
    """
    Initialize the database, creating tables if they don't exist.
    Returns a connection to the database.
    """
    # Ensure storage directory exists
    os.makedirs('storage', exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    
    # Create tables
    create_tables(conn)
    
    # Set schema version
    current_version = get_schema_version(conn)
    if current_version == 0:
        set_schema_version(conn, 1)
        logger.info("Database initialized with schema version 1")
    
    return conn

def migrate_from_json(conn: sqlite3.Connection, users_file: str, gamelogs_file: str):
    """
    Migrate data from JSON files to SQLite.
    This is a one-time migration for existing data.
    """
    import json
    from common.password_utils import hash_password
    
    cursor = conn.cursor()
    
    # Check if migration already done
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    if user_count > 0:
        logger.info("Database already has data, skipping JSON migration")
        return
    
    # Migrate users
    if os.path.exists(users_file):
        logger.info(f"Migrating users from {users_file}")
        with open(users_file, 'r') as f:
            users_data = json.load(f)
            
        for username, user_data in users_data.items():
            password = user_data.get('password', '')
            # Hash existing plaintext passwords
            password_hash = hash_password(password) if password else hash_password('default')
            status = user_data.get('status', 'offline')
            
            cursor.execute("""
                INSERT OR IGNORE INTO users (username, password_hash, status)
                VALUES (?, ?, ?)
            """, (username, password_hash, status))
        
        logger.info(f"Migrated {len(users_data)} users")
    
    # Migrate game logs
    if os.path.exists(gamelogs_file):
        logger.info(f"Migrating game logs from {gamelogs_file}")
        with open(gamelogs_file, 'r') as f:
            logs_data = json.load(f)
            
        for log in logs_data:
            cursor.execute("""
                INSERT OR IGNORE INTO game_logs 
                (matchid, game_id, users, results, winner, reason, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.get('matchid'),
                log.get('game_id'),  # May be None for old logs
                json.dumps(log.get('users', [])),
                json.dumps(log.get('results', [])),
                log.get('winner'),
                log.get('reason'),
                log.get('start_time'),
                log.get('end_time')
            ))
        
        logger.info(f"Migrated {len(logs_data)} game logs")
    
    conn.commit()
    logger.info("JSON migration completed")

