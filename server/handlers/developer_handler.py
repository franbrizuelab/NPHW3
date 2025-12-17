# Developer handler
# Handles game upload, update, and removal (developer-only actions)

import socket
import os
import hashlib
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

def forward_to_db(request: dict, db_host: str, db_port: int) -> dict | None:
    """Forward request to database server."""
    from common.protocol import send_msg, recv_msg
    import json
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((db_host, db_port))
            request_bytes = json.dumps(request).encode('utf-8')
            send_msg(sock, request_bytes)
            response_bytes = recv_msg(sock)
            
            if response_bytes:
                return json.loads(response_bytes.decode('utf-8'))
            else:
                logger.warning("DB server closed connection unexpectedly.")
                return {"status": "error", "reason": "db_server_no_response"}
    except Exception as e:
        logger.error(f"Failed to communicate with DB server: {e}")
        return {"status": "error", "reason": f"db_server_error: {e}"}

def send_to_client(client_sock: socket.socket, response: dict):
    """Send response to client."""
    from common.protocol import send_msg
    import json
    
    try:
        response_bytes = json.dumps(response).encode('utf-8')
        send_msg(client_sock, response_bytes)
    except Exception as e:
        logger.warning(f"Failed to send message to client: {e}")

def check_developer(username: str, db_host: str, db_port: int) -> bool:
    """Check if user is a developer."""
    if not username:
        logger.warning("check_developer called with None or empty username")
        return False
    
    # Use "get" action to query user without password
    db_request = {
        "collection": "User",
        "action": "get",
        "data": {"username": username}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        user = db_response.get("user", {})
        is_dev = user.get("is_developer", False)
        logger.info(f"Developer check for {username}: {is_dev}")
        return is_dev
    else:
        logger.warning(f"Failed to check developer status for {username}: {db_response}")
    return False

def calculate_file_hash(file_data: bytes) -> str:
    """Calculate SHA256 hash of file data."""
    return hashlib.sha256(file_data).hexdigest()

def read_game_from_developer_folder(file_name: str) -> bytes | None:
    """
    Read a game file from developer/games/ folder.
    Returns file data as bytes, or None if file not found.
    """
    developer_games_dir = os.path.join("developer", "games")
    file_path = os.path.join(developer_games_dir, file_name)
    
    # Security: Ensure file is within developer/games directory (prevent path traversal)
    abs_developer_dir = os.path.abspath(developer_games_dir)
    abs_file_path = os.path.abspath(file_path)
    
    if not abs_file_path.startswith(abs_developer_dir):
        logger.error(f"Invalid file path: {file_name} (path traversal attempt?)")
        return None
    
    try:
        if not os.path.exists(file_path):
            logger.error(f"Game file not found: {file_path}")
            return None
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        logger.info(f"Read game file from developer folder: {file_path} ({len(file_data)} bytes)")
        return file_data
    except Exception as e:
        logger.error(f"Error reading game file from developer folder: {e}")
        return None

def save_game_file(game_id: int, version: str, file_data: bytes, storage_dir: str = "storage/games") -> Optional[str]:
    """Save game file to storage. Returns file path or None."""
    try:
        # Ensure storage directory exists
        os.makedirs(storage_dir, exist_ok=True)
        # Create directory structure: storage/games/{game_id}/v{version}/
        game_dir = os.path.join(storage_dir, str(game_id), f"v{version}")
        os.makedirs(game_dir, exist_ok=True)
        
        # Save as game.py (changed from game_server.py to match plan)
        file_path = os.path.join(game_dir, "game.py")
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        logger.info(f"Saved game file to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving game file: {e}")
        return None

def handle_upload_game(client_sock: socket.socket, username: str, data: dict,
                      db_host: str, db_port: int) -> dict:
    """Handle game upload (create new game)."""
    # Check developer status
    if not check_developer(username, db_host, db_port):
        return {"status": "error", "reason": "not_developer"}
    
    # Extract data
    name = data.get('name')
    description = data.get('description', '')
    version = data.get('version', '1.0.0')
    file_data_str = data.get('file_data')  # Base64 encoded file data (Mode 1)
    file_name = data.get('file_name')  # File name in developer/games/ (Mode 2)
    
    if not name:
        return {"status": "error", "reason": "missing_name"}
    
    # Mode 1: Direct file upload via base64
    # Mode 2: File reference from developer/games/
    file_data = None
    
    if file_data_str:
        # Mode 1: Decode base64 file data
        import base64
        try:
            file_data = base64.b64decode(file_data_str)
        except Exception as e:
            logger.error(f"Error decoding file data: {e}")
            return {"status": "error", "reason": "invalid_file_data"}
    elif file_name:
        # Mode 2: Read from developer/games/ folder
        file_data = read_game_from_developer_folder(file_name)
        if file_data is None:
            return {"status": "error", "reason": "file_not_found_in_developer_folder"}
    else:
        return {"status": "error", "reason": "missing_file_data_or_file_name"}
    
    # Calculate file hash
    file_hash = calculate_file_hash(file_data)
    
    # Create game in database
    db_request = {
        "collection": "Game",
        "action": "create",
        "data": {
            "name": name,
            "author": username,
            "description": description,
            "version": version
        }
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if not db_response or db_response.get("status") != "ok":
        return {"status": "error", "reason": "failed_to_create_game"}
    
    game_id = db_response.get("game_id")
    if not game_id:
        return {"status": "error", "reason": "no_game_id_returned"}
    
    # Save game file
    file_path = save_game_file(game_id, version, file_data)
    if not file_path:
        return {"status": "error", "reason": "failed_to_save_file"}
    
    # Create game version entry
    db_version_request = {
        "collection": "GameVersion",
        "action": "create",
        "data": {
            "game_id": game_id,
            "version": version,
            "file_path": file_path,
            "file_hash": file_hash
        }
    }
    db_version_response = forward_to_db(db_version_request, db_host, db_port)
    
    if not db_version_response or db_version_response.get("status") != "ok":
        logger.warning(f"Game created but version entry failed for game {game_id}")
    
    logger.info(f"User {username} uploaded game '{name}' (id: {game_id}, version: {version})")
    return {"status": "ok", "game_id": game_id, "version": version}

def handle_update_game(client_sock: socket.socket, username: str, data: dict,
                      db_host: str, db_port: int) -> dict:
    """Handle game update (add new version and update metadata)."""
    # Check developer status
    if not check_developer(username, db_host, db_port):
        return {"status": "error", "reason": "not_developer"}
    
    game_id = data.get('game_id')
    version = data.get('version')
    name = data.get('name')  # Game name can be updated
    file_data_str = data.get('file_data')  # Mode 1: base64
    file_name = data.get('file_name')  # Mode 2: from developer/games/
    description = data.get('description', '')  # Description can be empty
    
    if not game_id or not version:
        return {"status": "error", "reason": "missing_game_id_or_version"}
    
    if not name:
        return {"status": "error", "reason": "missing_game_name"}
    
    if not file_data_str and not file_name:
        # Update metadata only (no new file)
        db_request = {
            "collection": "Game",
            "action": "update",
            "data": {
                "game_id": game_id,
                "name": name,
                "description": description,
                "current_version": version
            }
        }
        db_response = forward_to_db(db_request, db_host, db_port)
        if db_response and db_response.get("status") == "ok":
            logger.info(f"User {username} updated game {game_id} metadata (no new file)")
            return {"status": "ok", "game_id": game_id, "version": version}
        return db_response if db_response else {"status": "error", "reason": "db_error"}
    
    # Verify user owns this game
    db_check_request = {
        "collection": "Game",
        "action": "query",
        "data": {"game_id": game_id}
    }
    db_check_response = forward_to_db(db_check_request, db_host, db_port)
    
    if not db_check_response or db_check_response.get("status") != "ok":
        return {"status": "error", "reason": "game_not_found"}
    
    game = db_check_response.get("game", {})
    if game.get("author") != username:
        return {"status": "error", "reason": "not_game_owner"}
    
    # Get file data - Mode 1 or Mode 2
    file_data = None
    if file_data_str:
        # Mode 1: Decode base64 file data
        import base64
        try:
            file_data = base64.b64decode(file_data_str)
        except Exception as e:
            logger.error(f"Error decoding file data: {e}")
            return {"status": "error", "reason": "invalid_file_data"}
    elif file_name:
        # Mode 2: Read from developer/games/ folder
        file_data = read_game_from_developer_folder(file_name)
        if file_data is None:
            return {"status": "error", "reason": "file_not_found_in_developer_folder"}
    
    # Calculate file hash
    file_hash = calculate_file_hash(file_data)
    
    # Save new version
    file_path = save_game_file(game_id, version, file_data)
    if not file_path:
        return {"status": "error", "reason": "failed_to_save_file"}
    
    # Create version entry
    db_version_request = {
        "collection": "GameVersion",
        "action": "create",
        "data": {
            "game_id": game_id,
            "version": version,
            "file_path": file_path,
            "file_hash": file_hash
        }
    }
    db_version_response = forward_to_db(db_version_request, db_host, db_port)
    
    if not db_version_response or db_version_response.get("status") != "ok":
        return {"status": "error", "reason": "failed_to_create_version"}
    
    # Update game's metadata (name, description, current_version) - completely replace previous values
    db_update_request = {
        "collection": "Game",
        "action": "update",
        "data": {
            "game_id": game_id,
            "name": name,  # Update name
            "description": description,  # Update description (can be empty string)
            "current_version": version  # Update version
        }
    }
    db_update_response = forward_to_db(db_update_request, db_host, db_port)
    
    if not db_update_response or db_update_response.get("status") != "ok":
        logger.error(f"Failed to update game metadata for game {game_id}")
        return {"status": "error", "reason": "failed_to_update_metadata"}
    
    logger.info(f"User {username} updated game {game_id} to version {version} (name: {name})")
    return {"status": "ok", "game_id": game_id, "version": version}

def handle_remove_game(client_sock: socket.socket, username: str, data: dict,
                      db_host: str, db_port: int) -> dict:
    """Handle game removal."""
    # Check developer status
    if not check_developer(username, db_host, db_port):
        return {"status": "error", "reason": "not_developer"}
    
    game_id = data.get('game_id')
    if not game_id:
        return {"status": "error", "reason": "missing_game_id"}
    
    # Verify user owns this game
    db_check_request = {
        "collection": "Game",
        "action": "query",
        "data": {"game_id": game_id}
    }
    db_check_response = forward_to_db(db_check_request, db_host, db_port)
    
    if not db_check_response or db_check_response.get("status") != "ok":
        return {"status": "error", "reason": "game_not_found"}
    
    game = db_check_response.get("game", {})
    if game.get("author") != username:
        return {"status": "error", "reason": "not_game_owner"}
    
    # Soft delete: Mark game as deleted in database (keep files and records)
    # Game files are kept for potential restoration or record-keeping
    db_request = {
        "collection": "Game",
        "action": "delete",
        "data": {"game_id": game_id}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        logger.info(f"User {username} soft-deleted game {game_id} (marked as deleted, files kept)")
        return {"status": "ok"}
    else:
        return {"status": "error", "reason": "failed_to_delete_game"}

