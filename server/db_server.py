# Standalone Database Server.
#
# TCP server that listens on a dedicated port.
# Uses the Length-Prefixed Framing Protocol from common.protocol.
# All requests and responses are JSON strings.
# Persists data to SQLite database.
# Uses threading to handle multiple concurrent clients.

import socket
import threading
import json
import os
import sys
import logging
import sqlite3

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import our new protocol functions
try:
    from common import config
    from common.protocol import send_msg, recv_msg
    from common.db_schema import initialize_database, migrate_from_json
    from common.db_operations import DatabaseOperations
    from common.password_utils import hash_password, verify_password
except ImportError as e:
    print(f"Error: Could not import required modules: {e}")
    print("Ensure all common modules exist and are in your Python path.")
    sys.exit(1)

# Server Configuration
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
STORAGE_DIR = 'storage'
USER_DB_FILE = os.path.join(STORAGE_DIR, 'users.json')
GAMELOG_DB_FILE = os.path.join(STORAGE_DIR, 'gamelogs.json')

# Database connection (shared across threads, SQLite handles thread-safety)
db_conn = None
db_ops = None
db_lock = threading.Lock()  # For operations that need explicit locking

# Configure logging
logging.basicConfig(level=logging.INFO, format='[DB_SERVER] %(asctime)s - %(message)s')

# Database Helper Functions

def setup_database():
    """Initialize SQLite database and migrate from JSON if needed."""
    global db_conn, db_ops
    
    try:
        # Initialize database
        db_conn = initialize_database()
        db_ops = DatabaseOperations(db_conn)
        
        # Migrate from JSON files if they exist
        if os.path.exists(USER_DB_FILE) or os.path.exists(GAMELOG_DB_FILE):
            logging.info("JSON files detected, migrating to SQLite...")
            migrate_from_json(db_conn, USER_DB_FILE, GAMELOG_DB_FILE)
            logging.info("Migration completed")
        
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.critical(f"Failed to initialize database: {e}")
        sys.exit(1)

# Request Processing Logic

def process_request(request_data: dict) -> dict:
    # Main logic to handle a parsed JSON request.
    try:
        collection = request_data['collection']
        action = request_data['action']
        data = request_data.get('data', {})

        # === User Collection ===
        if collection == "User":
            if action == "create":  # Register
                username = data.get('username')
                password = data.get('password')
                if not username or not password:
                    return {"status": "error", "reason": "missing_fields"}
                
                # Check if user already exists
                existing_user = db_ops.get_user(username)
                if existing_user:
                    return {"status": "error", "reason": "user_exists"}
                
                # Hash password before storing
                password_hash = hash_password(password)
                is_developer = data.get('is_developer', False)
                
                # Create user
                if db_ops.create_user(username, password_hash, is_developer):
                    logging.info(f"Registered new user: {username}")
                    return {"status": "ok"}
                else:
                    return {"status": "error", "reason": "user_exists"}

            elif action == "query": # Login
                username = data.get('username')
                password = data.get('password')
                if not username or not password:
                    return {"status": "error", "reason": "missing_fields"}
                
                user = db_ops.get_user(username)
                if user and verify_password(password, user['password_hash']):
                    logging.info(f"User login successful: {username}")
                    # Return user data (excluding password_hash, but include is_developer)
                    return {
                        "status": "ok",
                        "user": {
                            "username": username,
                            "is_developer": bool(user.get('is_developer', 0))
                        }
                    }
                else:
                    logging.warning(f"User login failed: {username}")
                    return {"status": "error", "reason": "invalid_credentials"}
            
            elif action == "update": # For setting status
                username = data.get('username')
                new_status = data.get('status')
                
                if not username or not new_status:
                    return {"status": "error", "reason": "missing_fields_for_update"}
                
                if db_ops.update_user_status(username, new_status):
                    logging.info(f"Updated status for {username} to {new_status}")
                    return {"status": "ok"}
                else:
                    return {"status": "error", "reason": "user_not_found"}
                
            else:
                return {"status": "error", "reason": f"Unknown action '{action}' for User"}

        # === GameLog Collection ===
        elif collection == "GameLog":
            if action == "create": # Save a game result
                if not data:
                    return {"status": "error", "reason": "missing_gamelog_data"}
                
                # Extract data
                matchid = data.get('matchid')
                game_id = data.get('game_id')
                users = data.get('users', [])
                results = data.get('results', [])
                winner = data.get('winner')
                reason = data.get('reason')
                start_time = data.get('start_time')
                end_time = data.get('end_time')
                
                if db_ops.create_game_log(matchid, game_id, users, results, winner, reason, start_time, end_time):
                    logging.info(f"Saved new gamelog for match: {matchid}")
                    return {"status": "ok"}
                else:
                    return {"status": "error", "reason": "gamelog_already_exists"}

            elif action == "query": # Get game logs (e.g., for a user)
                logging.info(f"Received query for GameLog with data: {data}")
                user_id = data.get('userId')
                
                logs = db_ops.get_game_logs(user_id)
                # Convert to format expected by clients
                formatted_logs = []
                for log in logs:
                    formatted_logs.append({
                        'matchid': log['matchid'],
                        'game_id': log.get('game_id'),
                        'users': log['users'],
                        'results': log['results'],
                        'winner': log.get('winner'),
                        'reason': log.get('reason'),
                        'start_time': log.get('start_time'),
                        'end_time': log.get('end_time')
                    })
                
                return {"status": "ok", "logs": formatted_logs}

            else:
                return {"status": "error", "reason": f"Unknown action '{action}' for GameLog"}

        # === Game Collection ===
        elif collection == "Game":
            if action == "create":
                name = data.get('name')
                author = data.get('author')
                description = data.get('description')
                version = data.get('version')
                
                if not name or not author:
                    return {"status": "error", "reason": "missing_fields"}
                
                game_id = db_ops.create_game(name, author, description, version)
                if game_id:
                    logging.info(f"Created game: {name} (id: {game_id})")
                    return {"status": "ok", "game_id": game_id}
                else:
                    return {"status": "error", "reason": "failed_to_create_game"}
            
            elif action == "query":
                game_id = data.get('game_id')
                if game_id:
                    game = db_ops.get_game(game_id)
                    if game:
                        return {"status": "ok", "game": game}
                    else:
                        return {"status": "error", "reason": "game_not_found"}
                else:
                    return {"status": "error", "reason": "missing_game_id"}
            
            elif action == "list":
                games = db_ops.list_all_games()
                return {"status": "ok", "games": games}
            
            elif action == "list_by_author":
                author = data.get('author')
                if not author:
                    return {"status": "error", "reason": "missing_author"}
                games = db_ops.get_games_by_author(author)
                return {"status": "ok", "games": games}
            
            elif action == "search":
                query = data.get('query', '')
                if not query:
                    return {"status": "error", "reason": "missing_query"}
                games = db_ops.search_games(query)
                return {"status": "ok", "games": games}
            
            elif action == "update":
                game_id = data.get('game_id')
                if not game_id:
                    return {"status": "error", "reason": "missing_game_id"}
                
                name = data.get('name')
                description = data.get('description')
                current_version = data.get('current_version')
                
                if db_ops.update_game(game_id, name, description, current_version):
                    return {"status": "ok"}
                else:
                    return {"status": "error", "reason": "failed_to_update_game"}
            
            elif action == "delete":
                game_id = data.get('game_id')
                if not game_id:
                    return {"status": "error", "reason": "missing_game_id"}
                
                if db_ops.delete_game(game_id):
                    return {"status": "ok"}
                else:
                    return {"status": "error", "reason": "failed_to_delete_game"}
            
            else:
                return {"status": "error", "reason": f"Unknown action '{action}' for Game"}

        # === GameVersion Collection ===
        elif collection == "GameVersion":
            if action == "create":
                game_id = data.get('game_id')
                version = data.get('version')
                file_path = data.get('file_path')
                file_hash = data.get('file_hash')
                
                if not game_id or not version or not file_path:
                    return {"status": "error", "reason": "missing_fields"}
                
                version_id = db_ops.create_game_version(game_id, version, file_path, file_hash)
                if version_id:
                    return {"status": "ok", "version_id": version_id}
                else:
                    return {"status": "error", "reason": "failed_to_create_version"}
            
            elif action == "query":
                game_id = data.get('game_id')
                version = data.get('version')
                
                if not game_id:
                    return {"status": "error", "reason": "missing_game_id"}
                
                if version:
                    version_info = db_ops.get_game_version(game_id, version)
                else:
                    version_info = db_ops.get_latest_version(game_id)
                
                if version_info:
                    return {"status": "ok", "version": version_info}
                else:
                    return {"status": "error", "reason": "version_not_found"}
            
            else:
                return {"status": "error", "reason": f"Unknown action '{action}' for GameVersion"}

        else:
            return {"status": "error", "reason": f"Unknown collection '{collection}'"}

    except KeyError as e:
        logging.warning(f"Request processing error: Missing key {e}")
        return {"status": "error", "reason": f"missing_key: {e}"}
    except Exception as e:
        logging.error(f"Unexpected error in process_request: {e}", exc_info=True)
        return {"status": "error", "reason": "internal_server_error"}


# Client Handling Thread

def handle_client(client_socket: socket.socket, addr: tuple):
    """
    Runs in a separate thread for each connected client.
    Handles one request/response cycle per connection.
    """
    logging.info(f"Client connected from {addr}")
    response_data = {}
    
    try:
        # 1. Receive a message using our protocol
        request_bytes = recv_msg(client_socket)
        
        if request_bytes is None:
            logging.info(f"Client {addr} disconnected before sending data.")
            return

        # 2. Decode from bytes to string and parse JSON
        try:
            request_str = request_bytes.decode('utf-8')
            request_data = json.loads(request_str)
            logging.info(f"Received from {addr}: {request_data}")
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logging.warning(f"Failed to decode/parse JSON from {addr}: {e}")
            response_data = {"status": "error", "reason": "invalid_json_format"}
            return # 'finally' block will send this response

        # 3. Process the request
        response_data = process_request(request_data)

    except socket.error as e:
        logging.warning(f"Socket error with client {addr}: {e}")
    except Exception as e:
        logging.error(f"Unhandled exception for client {addr}: {e}", exc_info=True)
        response_data = {"status": "error", "reason": "internal_server_error"}
        
    finally:
        # 4. Send the response
        try:
            if response_data: # Only send if we have a response
                response_bytes = json.dumps(response_data).encode('utf-8')
                send_msg(client_socket, response_bytes)
                logging.info(f"Sent to {addr}: {response_data}")
        except Exception as e:
            logging.error(f"Failed to send response to {addr}: {e}")
        
        # 5. Close the connection
        client_socket.close()
        logging.info(f"Connection closed for {addr}")

# Main Server Loop

def main():
    """Starts the DB server."""
    
    # 1. Initialize database
    setup_database()
    
    # 2. Create the server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        # 3. Bind and Listen
        server_socket.bind(('0.0.0.0', DB_PORT))
        server_socket.listen()
        logging.info(f"Database Server listening on {DB_HOST}:{DB_PORT}...")
        logging.info("Press Ctrl+C to stop.")

        # 4. Accept connections
        while True:
            try:
                # Wait for a client
                client_socket, addr = server_socket.accept()
                
                # Create and start a new thread to handle this client
                # Allows server to handle multiple clients at once
                client_thread = threading.Thread(
                    target=handle_client, 
                    args=(client_socket, addr)
                )
                client_thread.daemon = True # Allows server to exit even if threads are running
                client_thread.start()
                
            except socket.error as e:
                logging.error(f"Socket error while accepting connections: {e}")

    except KeyboardInterrupt:
        logging.info("Shutting down database server.")
    except Exception as e:
        logging.critical(f"A critical error occurred: {e}", exc_info=True)
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()
