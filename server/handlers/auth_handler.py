# Authentication handler
# Handles user registration, login, and logout

import socket
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def forward_to_db(request: dict, db_host: str, db_port: int) -> dict | None:
    """
    Acts as a client to the DB_Server.
    Opens a new connection, sends one request, gets one response.
    """
    from common.protocol import send_msg, recv_msg
    import json
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((db_host, db_port))
            
            # 1. Send request
            request_bytes = json.dumps(request).encode('utf-8')
            send_msg(sock, request_bytes)
            
            # 2. Receive response
            response_bytes = recv_msg(sock)
            
            if response_bytes:
                return json.loads(response_bytes.decode('utf-8'))
            else:
                logger.warning("DB server closed connection unexpectedly.")
                return {"status": "error", "reason": "db_server_no_response"}
                
    except socket.error as e:
        logger.error(f"Failed to connect or communicate with DB server: {e}")
        return {"status": "error", "reason": f"db_server_connection_error: {e}"}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to decode DB server response: {e}")
        return {"status": "error", "reason": "db_server_bad_response"}

def send_to_client(client_sock: socket.socket, response: dict):
    """Encodes and sends a JSON response to a client."""
    from common.protocol import send_msg
    import json
    
    try:
        response_bytes = json.dumps(response).encode('utf-8')
        send_msg(client_sock, response_bytes)
    except Exception as e:
        logger.warning(f"Failed to send message to client: {e}")

def handle_register(client_sock: socket.socket, data: dict, db_host: str, db_port: int) -> dict:
    """Handles 'register' action."""
    username = data.get('user')
    password = data.get('pass')
    is_developer = data.get('is_developer', False) # Check for the new flag
    
    if not username or not password:
        return {"status": "error", "reason": "missing_fields"}

    # Prepare data for DB server, including the developer flag
    db_data = {
        "username": username,
        "password": password,
        "is_developer": is_developer
    }
    
    # Forward to DB server
    db_request = {
        "collection": "User",
        "action": "create",
        "data": db_data
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    # Pass the DB response directly back to the client
    return db_response

def handle_login(client_sock: socket.socket, addr: tuple, data: dict, 
                db_host: str, db_port: int,
                client_sessions: dict, session_lock: threading.Lock) -> str | None:
    """
    Handles 'login' action.
    If successful, adds user to client_sessions and returns username.
    If failed, returns None.
    """
    
    username = data.get('user')
    password = data.get('pass')
    
    if not username or not password:
        send_to_client(client_sock, {"status": "error", "reason": "missing_fields"})
        return None

    # Check if already logged in
    with session_lock:
        if username in client_sessions:
            send_to_client(client_sock, {"status": "error", "reason": "already_logged_in"})
            return None

    # Forward to DB server to validate
    db_request = {
        "collection": "User",
        "action": "query",
        "data": {
            "username": username,
            "password": password
        }
    }
    db_response = forward_to_db(db_request, db_host, db_port)
    
    if db_response and db_response.get("status") == "ok":
        # Login successful!
        logger.info(f"User '{username}' logged in from {addr}.")
        
        # Add to our live session tracking
        with session_lock:
            client_sessions[username] = {
                "sock": client_sock,
                "addr": addr,
                "status": "online"
            }
        
        db_status_update_req = {
            "collection": "User",
            "action": "update",
            "data": {"username": username, "status": "online"}
        }
        db_status_response = forward_to_db(db_status_update_req, db_host, db_port)
        if not db_status_response or db_status_response.get("status") != "ok":
            # Log a warning, but don't fail the login
            logger.warning(f"Failed to update 'online' status in DB for {username}.")

        # Send success to client
        send_to_client(client_sock, {"status": "ok", "reason": "login_successful"})
        
        return username
    else:
        # Login failed
        logger.warning(f"Failed login attempt for '{username}'.")
        reason = db_response.get("reason", "invalid_credentials") if db_response else "invalid_credentials"
        send_to_client(client_sock, {"status": "error", "reason": reason})
        return None

def handle_logout(username: str, db_host: str, db_port: int,
                 client_sessions: dict, session_lock: threading.Lock,
                 rooms: dict, room_lock: threading.Lock):
    """
    Handles 'logout' action or clean-up on disconnect.
    """
    
    if not username:
        return

    session_status = ""
    session_sock = None

    with session_lock:
        session = client_sessions.pop(username, None)
        if session:
            session_status = session.get("status", "online")
            session_sock = session.get("sock")
    
    if session:
        logger.info(f"User '{username}' logged out.")
        
        # 1. Update DB status
        db_status_update_req = {
            "collection": "User", "action": "update",
            "data": {"username": username, "status": "offline"}
        }
        db_status_response = forward_to_db(db_status_update_req, db_host, db_port)
        if not db_status_response or db_status_response.get("status") != "ok":
            logger.warning(f"Failed to update 'offline' status in DB for {username}.")

        # 2. Check if user was in an "idle" room
        if session_status.startswith("in_room_"):
            try:
                room_id = int(session_status.split('_')[-1])
                with room_lock:
                    room = rooms.get(room_id)
                    if room:
                        # Only clean up if the room was IDLE.
                        # If "playing", the game server is in charge.
                        if room["status"] == "idle":
                            if username in room["players"]:
                                room["players"].remove(username)
                            
                            if not room["players"]:
                                del rooms[room_id]
                                logger.info(f"Room {room_id} is empty, deleting.")
                            elif room["host"] == username:
                                room["host"] = room["players"][0]
                                new_host = room["host"]
                                logger.info(f"Host {username} left idle room, promoting {new_host}.")
                        
            except (ValueError, IndexError):
                logger.warning(f"Could not parse room ID from status: {session_status}")
        
        # 3. Send final confirmation
        if session_sock:
            try:
                send_to_client(session_sock, {"status": "ok", "reason": "logout_successful"})
                session_sock.close()
            except Exception as e:
                logger.warning(f"Error during final logout send for {username}: {e}")

