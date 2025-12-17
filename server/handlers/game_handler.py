# Game handler
# Handles game browsing, search, and download (available to all users)

import socket
import os
import logging

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

def handle_list_games(client_sock: socket.socket, db_host: str, db_port: int):
    """Handle list all games."""
    db_request = {
        "collection": "Game",
        "action": "list"
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        games = db_response.get("games", [])
        send_to_client(client_sock, {"status": "ok", "games": games})
    else:
        send_to_client(client_sock, {"status": "error", "reason": "failed_to_list_games"})

def handle_search_games(client_sock: socket.socket, data: dict, db_host: str, db_port: int):
    """Handle game search."""
    query = data.get('query', '')
    if not query:
        send_to_client(client_sock, {"status": "error", "reason": "missing_query"})
        return
    
    db_request = {
        "collection": "Game",
        "action": "search",
        "data": {"query": query}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        games = db_response.get("games", [])
        send_to_client(client_sock, {"status": "ok", "games": games})
    else:
        send_to_client(client_sock, {"status": "error", "reason": "failed_to_search_games"})

def handle_get_game_info(client_sock: socket.socket, data: dict, db_host: str, db_port: int):
    """Handle get game info."""
    game_id = data.get('game_id')
    if not game_id:
        send_to_client(client_sock, {"status": "error", "reason": "missing_game_id"})
        return
    
    db_request = {
        "collection": "Game",
        "action": "query",
        "data": {"game_id": game_id}
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        game = db_response.get("game", {})
        send_to_client(client_sock, {"status": "ok", "game": game})
    else:
        send_to_client(client_sock, {"status": "error", "reason": "game_not_found"})

def handle_download_game(client_sock: socket.socket, data: dict, db_host: str, db_port: int):
    """Handle game download."""
    game_id = data.get('game_id')
    version = data.get('version')  # Optional, defaults to current_version
    
    if not game_id:
        send_to_client(client_sock, {"status": "error", "reason": "missing_game_id"})
        return
    
    # Get game info
    db_game_request = {
        "collection": "Game",
        "action": "query",
        "data": {"game_id": game_id}
    }
    db_game_response = forward_to_db(db_game_request, db_host, db_port)
    
    if not db_game_response or db_game_response.get("status") != "ok":
        send_to_client(client_sock, {"status": "error", "reason": "game_not_found"})
        return
    
    game = db_game_response.get("game", {})
    if not version:
        version = game.get("current_version", "1.0.0")
    
    # Get version info
    db_version_request = {
        "collection": "GameVersion",
        "action": "query",
        "data": {"game_id": game_id, "version": version}
    }
    db_version_response = forward_to_db(db_version_request, db_host, db_port)
    
    if not db_version_response or db_version_response.get("status") != "ok":
        send_to_client(client_sock, {"status": "error", "reason": "version_not_found"})
        return
    
    version_info = db_version_response.get("version", {})
    file_path = version_info.get("file_path")
    
    if not file_path or not os.path.exists(file_path):
        send_to_client(client_sock, {"status": "error", "reason": "file_not_found"})
        return
    
    # Read and encode file
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        import base64
        file_data_b64 = base64.b64encode(file_data).decode('utf-8')
        
        send_to_client(client_sock, {
            "status": "ok",
            "action": "download_game",  # Include action for client to identify response
            "game_id": game_id,
            "game_name": game.get("name"),  # Include game name for file naming
            "version": version,
            "file_data": file_data_b64,
            "file_hash": version_info.get("file_hash")
        })
        logger.info(f"Sent game {game_id} version {version} to client")
    except Exception as e:
        logger.error(f"Error reading game file: {e}")
        send_to_client(client_sock, {"status": "error", "reason": "failed_to_read_file"})

