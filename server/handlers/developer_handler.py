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
    db_request = {
        "collection": "User",
        "action": "query",
        "data": {"username": username}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        user = db_response.get("user", {})
        return user.get("is_developer", False)
    return False

def calculate_file_hash(file_data: bytes) -> str:
    """Calculate SHA256 hash of file data."""
    return hashlib.sha256(file_data).hexdigest()

def save_game_file(game_id: int, version: str, file_data: bytes, storage_dir: str = "storage/games") -> Optional[str]:
    """Save game file to storage. Returns file path or None."""
    try:
        # Ensure storage directory exists
        os.makedirs(storage_dir, exist_ok=True)
        # Create directory structure: storage/games/{game_id}/v{version}/
        game_dir = os.path.join(storage_dir, str(game_id), f"v{version}")
        os.makedirs(game_dir, exist_ok=True)
        
        # Save game_server.py
        file_path = os.path.join(game_dir, "game_server.py")
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
    file_data_str = data.get('file_data')  # Base64 encoded or raw bytes
    
    if not name or not file_data_str:
        return {"status": "error", "reason": "missing_fields"}
    
    # Decode file data (assuming base64)
    import base64
    try:
        file_data = base64.b64decode(file_data_str)
    except Exception as e:
        logger.error(f"Error decoding file data: {e}")
        return {"status": "error", "reason": "invalid_file_data"}
    
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
    """Handle game update (add new version)."""
    # Check developer status
    if not check_developer(username, db_host, db_port):
        return {"status": "error", "reason": "not_developer"}
    
    game_id = data.get('game_id')
    version = data.get('version')
    file_data_str = data.get('file_data')
    description = data.get('description')
    
    if not game_id or not version:
        return {"status": "error", "reason": "missing_game_id_or_version"}
    
    if not file_data_str:
        # Update metadata only
        db_request = {
            "collection": "Game",
            "action": "update",
            "data": {
                "game_id": game_id,
                "description": description
            }
        }
        db_response = forward_to_db(db_request, db_host, db_port)
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
    
    # Decode file data
    import base64
    try:
        file_data = base64.b64decode(file_data_str)
    except Exception as e:
        logger.error(f"Error decoding file data: {e}")
        return {"status": "error", "reason": "invalid_file_data"}
    
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
    
    # Update game's current_version
    db_update_request = {
        "collection": "Game",
        "action": "update",
        "data": {
            "game_id": game_id,
            "current_version": version,
            "description": description
        }
    }
    forward_to_db(db_update_request, db_host, db_port)
    
    logger.info(f"User {username} updated game {game_id} to version {version}")
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
    
    # Delete game files
    game_dir = os.path.join("storage/games", str(game_id))
    if os.path.exists(game_dir):
        import shutil
        try:
            shutil.rmtree(game_dir)
            logger.info(f"Deleted game files for game {game_id}")
        except Exception as e:
            logger.error(f"Error deleting game files: {e}")
    
    # Delete from database
    db_request = {
        "collection": "Game",
        "action": "delete",
        "data": {"game_id": game_id}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        logger.info(f"User {username} removed game {game_id}")
        return {"status": "ok"}
    else:
        return {"status": "error", "reason": "failed_to_delete_game"}

