# player/player_client.py

import sys
import os
import logging
import base64
import argparse
import time
import threading
import socket
import select
import queue
import json
import pygame

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Go up one level
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.base_gui import BaseGUI, draw_text, Button, TextInput, BASE_CONFIG
from client.shared import send_to_lobby_queue, g_lobby_send_queue
from common import protocol

# Predefined users for auto-login
PLAYER_USERS = {
    1: {"user": "player1", "pass": "player1"},
    2: {"user": "player2", "pass": "player2"},
    3: {"user": "player3", "pass": "player3"}
}

class PlayerGUI(BaseGUI):
    def __init__(self, auto_login_user=None):
        super().__init__(title="Player Client")
        self.all_games = [] # Games available in the store
        self.my_games = []  # Games downloaded by the player
        self.game_rooms = [] # Available rooms in the lobby
        self.download_buttons = {}  # Maps game_id to Button object
        self.create_room_buttons = {}  # Maps game_id to Button object
        self.auto_login_user = auto_login_user  # User credentials for auto-login
        self.auto_login_sent = False  # Track if auto-login has been sent
        
        # Version checking and tracking
        self.version_check_interval = 30  # seconds
        self.last_version_check = 0
        self.downloaded_versions = {}  # Maps game_id to {"version": str, "downloaded_at": float}
        
        # Room creation state
        self.room_is_public = True  # Default to public rooms
        self.online_users = []  # List of online users for invitations
        self.invite_buttons = {}  # Maps username to invite button
        self.room_toggle_buttons = {}  # Maps game_id to toggle button
        self.current_room_game_id = None  # Track which game we're creating room for
        
        # Room state
        self.current_room_id = None  # Current room ID if in a room
        self.current_room_data = {}  # Current room data (players, host, etc.)
        self.room_join_buttons = {}  # Maps room_id to join button
        
        # Invitation popup state
        self.pending_invite = None  # Stores invite data: {"from_user": str, "room_id": int, "game_name": str}
        self.invite_accept_btn = None
        self.invite_decline_btn = None

    def _lobby_network_thread(self):
        """Override base network thread to handle disconnections gracefully."""
        host, port = BASE_CONFIG["NETWORK"]["HOST"], BASE_CONFIG["NETWORK"]["PORT"]
        while self.running:
            if not self.lobby_socket:
                try:
                    logging.info(f"Connecting to lobby at {host}:{port}...")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((host, port))
                    self.lobby_socket = sock
                    logging.info("Connection successful.")
                    with self.state_lock:
                        if self.client_state == "CONNECTING": self.client_state = "LOGIN"
                except socket.error:
                    with self.state_lock:
                        if self.client_state == "CONNECTING": self.client_state = "ERROR"; self.error_message = "Lobby is offline."
                    time.sleep(2)
                    continue
            try:
                readable, _, exceptional = select.select([self.lobby_socket], [], [self.lobby_socket], 0.1)
                if exceptional: raise ConnectionError("Socket exceptional condition")
                if self.lobby_socket in readable:
                    data_bytes = protocol.recv_msg(self.lobby_socket)
                    if data_bytes is None: raise ConnectionError("Server closed connection")
                    self.handle_network_message(json.loads(data_bytes.decode('utf-8')))
                while not g_lobby_send_queue.empty():
                    request = g_lobby_send_queue.get_nowait()
                    protocol.send_msg(self.lobby_socket, json.dumps(request).encode('utf-8'))
                    if request.get("action") == "logout": raise ConnectionError("Logout initiated")
            except (ConnectionError, socket.error, json.JSONDecodeError, queue.Empty) as e:
                logging.warning(f"Network event: {e}")
                if self.lobby_socket: self.lobby_socket.close()
                self.lobby_socket = None
                with self.state_lock:
                    if self.client_state == "LOGGING_OUT": 
                        self.client_state = "LOGIN"
                        self.username = None
                    else:
                        # If we were in a room, return to lobby gracefully
                        if self.client_state in ["ROOM_WAITING"]:
                            self.current_room_id = None
                            self.current_room_data = {}
                            self.client_state = "LOBBY_MENU"
                            self.error_message = "Connection lost. Returned to lobby."
                        else:
                            self.client_state = "ERROR"
                            self.error_message = "Connection lost"
    
    def _start_network_thread(self):
        super()._start_network_thread()
        
        # If auto-login is enabled, wait for connection and send login
        if self.auto_login_user:
            def auto_login_thread():
                # Wait for connection to be established
                max_wait = 10  # Wait up to 10 seconds
                waited = 0
                while waited < max_wait and not self.lobby_socket:
                    time.sleep(0.1)
                    waited += 0.1
                
                if self.lobby_socket:
                    # Wait a bit more for the connection to be fully ready
                    time.sleep(0.5)
                    logging.info(f"Auto-login as {self.auto_login_user['user']}")
                    send_to_lobby_queue({
                        "action": "login",
                        "data": {"user": self.auto_login_user["user"], "pass": self.auto_login_user["pass"]}
                    })
                    self.username = self.auto_login_user["user"]
                else:
                    logging.warning("Could not establish connection for auto-login")
            
            threading.Thread(target=auto_login_thread, daemon=True).start()

    def _create_ui_elements(self):
        super()._create_ui_elements()
        self.ui_elements["store_btn"] = Button(10, 10, 150, 40, self.fonts["SMALL"], "Store")
        self.ui_elements["my_games_btn"] = Button(170, 10, 150, 40, self.fonts["SMALL"], "My Games")

    def draw_custom_state(self, screen, state):
        # Draw username in upper center for all states
        if self.username:
            username_text = self.username
            text_width = self.fonts["SMALL"].size(username_text)[0]
            center_x = BASE_CONFIG["SCREEN"]["WIDTH"] // 2
            draw_text(screen, username_text, center_x - text_width // 2, 10, self.fonts["SMALL"], (200, 200, 200))
        
        if state == "LOBBY_MENU":
            self.draw_lobby_menu(screen)
        elif state == "STORE_MENU":
            self.draw_store_menu(screen)
        elif state == "MY_GAMES_MENU":
            self.draw_my_games_menu(screen)
        elif state == "ROOM_WAITING":
            self.draw_room_waiting_screen(screen)
        
        # Draw invitation popup if there's a pending invite (draws on top of everything)
        if self.pending_invite:
            self.draw_invite_popup(screen)

    def handle_custom_events(self, event, state):
        if state == "LOBBY_MENU":
            if self.ui_elements["store_btn"].handle_event(event):
                self.client_state = "STORE_MENU"
            if self.ui_elements["my_games_btn"].handle_event(event):
                self.scan_downloaded_games() # Rescan just in case
                self.client_state = "MY_GAMES_MENU"
        elif state == "STORE_MENU":
            # Handle download button clicks
            for game_id, btn in self.download_buttons.items():
                if btn.handle_event(event):
                    # Check if already downloaded
                    if self._is_game_downloaded(game_id):
                        logging.info(f"Game {game_id} already downloaded")
                        continue
                    # Send download request
                    send_to_lobby_queue({
                        "action": "download_game",
                        "data": {"game_id": game_id}
                    })
                    logging.info(f"Requested download for game {game_id}")
        elif state == "MY_GAMES_MENU":
            # Periodic version checking
            current_time = time.time()
            if current_time - self.last_version_check > self.version_check_interval:
                send_to_lobby_queue({"action": "list_games"})
                self.last_version_check = current_time
            
            # Handle create room button clicks
            for game_id, btn in self.create_room_buttons.items():
                if btn.handle_event(event):
                    # Create room immediately and go to waiting screen
                    self.current_room_game_id = game_id
                    # Clear previous room state
                    self.current_room_id = None
                    self.current_room_data = {}
                    self.online_users = []
                    if hasattr(self, 'invite_buttons'):
                        self.invite_buttons = {}
                    send_to_lobby_queue({
                        "action": "create_room",
                        "data": {
                            "game_id": game_id,
                            "is_public": self.room_is_public,
                            "name": f"{self.username}'s {self._get_game_name(game_id)} Room"
                        }
                    })
                    # Request online users list for invitations (will be requested again when ROOM_UPDATE is received)
                    send_to_lobby_queue({"action": "list_users"})
                    logging.info(f"Creating room for game {game_id}, going to waiting screen")
            
            # Handle private/public toggle button clicks
            for game_id, toggle_btn in self.room_toggle_buttons.items():
                if toggle_btn.handle_event(event):
                    # Toggle room privacy state
                    self.room_is_public = not self.room_is_public
                    logging.info(f"Room privacy toggled to: {'Public' if self.room_is_public else 'Private'}")
        
        elif state == "ROOM_WAITING":
            # Handle invite button clicks
            if hasattr(self, 'invite_buttons'):
                for username, invite_btn in self.invite_buttons.items():
                    if invite_btn.handle_event(event):
                        # Send invitation
                        if self.current_room_id:
                            send_to_lobby_queue({
                                "action": "invite",
                                "data": {
                                    "target_user": username,
                                    "room_id": self.current_room_id
                                }
                            })
                            logging.info(f"Inviting {username} to room {self.current_room_id}")
            
            # Handle start game button (host only)
            if hasattr(self, 'start_game_btn') and self.start_game_btn.handle_event(event):
                if self.current_room_data and self.current_room_data.get("host") == self.username:
                    send_to_lobby_queue({"action": "start_game"})
                    logging.info("Requesting game start")
            
            # Periodic refresh of online users list (only if room is not full and not playing)
            if self.current_room_data:
                players = self.current_room_data.get("players", [])
                room_status = self.current_room_data.get("status", "idle")
                if len(players) < 2 and room_status != "playing":
                    current_time = time.time()
                    if not hasattr(self, 'last_users_refresh'):
                        self.last_users_refresh = 0
                    if current_time - self.last_users_refresh > 5:  # Refresh every 5 seconds
                        send_to_lobby_queue({"action": "list_users"})
                        self.last_users_refresh = current_time
        
        # Handle invitation popup (works in any state)
        if self.pending_invite:
            if self.invite_accept_btn and self.invite_accept_btn.handle_event(event):
                # Accept invitation - join the room
                room_id = self.pending_invite['room_id']
                self.pending_invite = None  # Close popup
                send_to_lobby_queue({
                    "action": "join_room",
                    "data": {"room_id": room_id}
                })
                logging.info(f"Accepted invitation to room {room_id}")
            elif self.invite_decline_btn and self.invite_decline_btn.handle_event(event):
                # Decline invitation
                self.pending_invite = None  # Close popup
                logging.info("Declined invitation")

    def handle_network_message(self, msg):
        """Handles player-specific network messages."""
        msg_type = msg.get("type")
        status = msg.get("status")

        if msg_type == "all_games_list":
            self.all_games = msg.get("games", [])
            # Update download buttons when games list is received
            self._update_download_buttons()
        
        elif status == "ok" and msg.get("reason") == "login_successful":
            with self.state_lock:
                self.client_state = "LOBBY_MENU"
                self.error_message = None
            # Request games list and rooms list after login
            send_to_lobby_queue({"action": "list_games"})
            send_to_lobby_queue({"action": "list_rooms"})
        
        elif status == "ok" and "games" in msg:
            # Received games list from server (response to list_games action)
            games = msg.get("games", [])
            logging.info(f"Received {len(games)} games from server: {[g.get('name') for g in games]}")
            # Compare versions and mark updates
            self._compare_versions(games)
            self.all_games = games
            self._update_download_buttons()
            # Force UI update by ensuring state is correct
            with self.state_lock:
                if self.client_state in ["STORE_MENU", "MY_GAMES_MENU"]:
                    # State is already correct, just need to redraw
                    pass
        
        elif status == "ok" and "users" in msg:
            # Received users list from server (response to list_users action)
            users = msg.get("users", [])
            # Filter to only online users (exclude self and players already in room)
            room_players = self.current_room_data.get("players", []) if self.current_room_data else []
            self.online_users = [
                u for u in users 
                if u.get("status") == "online" 
                and u.get("username") != self.username
                and u.get("username") not in room_players
            ]
            logging.info(f"Received {len(self.online_users)} online users for invitations")
        
        elif status == "ok" and msg.get("action") == "download_game":
            # Game download response
            self._handle_game_download(msg)
        
        elif msg.get("type") == "ROOM_UPDATE":
            # Room update received (room created, player joined, etc.)
            self.current_room_id = msg.get("room_id")
            # Update or create room data
            if not self.current_room_data:
                self.current_room_data = {}
            self.current_room_data.update({
                "room_id": msg.get("room_id"),
                "name": msg.get("name", self.current_room_data.get("name")),
                "players": msg.get("players", []),
                "host": msg.get("host", self.current_room_data.get("host")),
                "game_id": msg.get("game_id", self.current_room_data.get("game_id")),
                "game_name": msg.get("game_name", self.current_room_data.get("game_name")),
                "is_public": msg.get("is_public", self.current_room_data.get("is_public", True)),
                "status": msg.get("status", self.current_room_data.get("status", "idle"))
            })
            # Transition to waiting screen if not already there
            with self.state_lock:
                if self.client_state != "ROOM_WAITING" and self.current_room_id:
                    self.client_state = "ROOM_WAITING"
            logging.info(f"Room update: room_id={self.current_room_id}, players={self.current_room_data.get('players')}")
            
            # Refresh online users list when room updates (to exclude players in room)
            # Only if room is not full
            players = self.current_room_data.get("players", [])
            if len(players) < 2:
                send_to_lobby_queue({"action": "list_users"})
        
        elif msg.get("type") == "KICKED_FROM_ROOM":
            # User was kicked from room (host left)
            logging.info(f"Kicked from room: {msg.get('reason')}")
            self.current_room_id = None
            self.current_room_data = {}
            with self.state_lock:
                self.client_state = "MY_GAMES_MENU"
        
        elif msg.get("type") == "INVITE_RECEIVED":
            # Received an invitation
            self.pending_invite = {
                "from_user": msg.get("from_user"),
                "room_id": msg.get("room_id"),
                "game_name": msg.get("game_name", "Unknown Game")
            }
            logging.info(f"Received invitation from {self.pending_invite['from_user']} for room {self.pending_invite['room_id']}")
            # Create buttons if they don't exist
            if not self.invite_accept_btn:
                self.invite_accept_btn = Button(300, 350, 140, 40, self.fonts["SMALL"], "Accept")
            if not self.invite_decline_btn:
                self.invite_decline_btn = Button(460, 350, 140, 40, self.fonts["SMALL"], "Decline")
        
        elif msg.get("type") == "GAME_OVER":
            # Game ended - return to lobby
            winner = msg.get('winner', 'Unknown')
            reason = msg.get('reason', 'unknown')
            logging.info(f"Game over: {winner} won (reason: {reason})")
            
            # Notify lobby server that game is over (if room_id is available)
            room_id = msg.get("room_id")
            if room_id:
                send_to_lobby_queue({
                    "action": "game_over",
                    "data": {"room_id": room_id}
                })
            
            # Reset room state
            self.current_room_id = None
            self.current_room_data = {}
            with self.state_lock:
                self.client_state = "LOBBY_MENU"
            # Request updated rooms and users list
            send_to_lobby_queue({"action": "list_rooms"})
            send_to_lobby_queue({"action": "list_users"})
        
        elif status == "ok" and "rooms" in msg:
            # Received rooms list from server
            self.game_rooms = msg.get("rooms", [])
            logging.info(f"Received {len(self.game_rooms)} public rooms")
        
        elif msg.get("type") == "GAME_START":
            # Game server started, transition to game
            game_host = msg.get("host")
            game_port = msg.get("port")
            room_id = msg.get("room_id")
            logging.info(f"Game started on {game_host}:{game_port} for room {room_id}")
            # Update room status to playing (room stays open)
            if self.current_room_data:
                self.current_room_data["status"] = "playing"
            # Note: The actual game connection will be handled by the game client
            # For now, we just update the room status to show "playing"
            # For now, stay in ROOM_WAITING screen but show game is running
        
        else:
            super().handle_network_message(msg)
    
    def _handle_game_download(self, msg):
        """Handle game download response and save file."""
        try:
            game_id = msg.get("game_id")
            version = msg.get("version")
            file_data_b64 = msg.get("file_data")
            # Get game name from response (preferred) or from all_games list
            game_name = msg.get("game_name")
            
            if not game_name:
                # Fallback: Find game name from all_games list
                for game in self.all_games:
                    if game.get("id") == game_id:
                        game_name = game.get("name", f"game_{game_id}")
                        break
            
            if not game_name:
                game_name = f"game_{game_id}"
            
            if not file_data_b64:
                logging.error("No file data in download response")
                return
            
            # Decode file data
            file_data = base64.b64decode(file_data_b64)
            
            # Save to user's download directory
            if not self.username:
                logging.error("Cannot download game: not logged in")
                return
            
            user_download_dir = os.path.join("player", "downloads", self.username)
            os.makedirs(user_download_dir, exist_ok=True)
            
            # Save as {game_name}.py
            file_path = os.path.join(user_download_dir, f"{game_name}.py")
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            logging.info(f"Downloaded game '{game_name}' to {file_path}")
            
            # Rescan downloaded games
            self.scan_downloaded_games()
            self._update_download_buttons()
            
        except Exception as e:
            logging.error(f"Error handling game download: {e}")
    
    def _update_download_buttons(self):
        """Update download buttons for games in store."""
        self.download_buttons = {}
        # Buttons will be created dynamically in draw_store_menu

    def handle_back_button(self, current_state):
        """Custom back button behavior for the player client."""
        with self.state_lock:
            if current_state == "ROOM_WAITING":
                # Leave the room and return to games page
                if self.current_room_id:
                    send_to_lobby_queue({
                        "action": "leave_room",
                        "data": {}
                    })
                    logging.info(f"Leaving room {self.current_room_id}")
                # Reset room state immediately (optimistic)
                self.current_room_id = None
                self.current_room_data = {}
                self.current_room_game_id = None
                if hasattr(self, 'invite_buttons'):
                    self.invite_buttons = {}
                # Return to MY_GAMES_MENU (not logout)
                self.client_state = "MY_GAMES_MENU"
            elif current_state in ["STORE_MENU", "MY_GAMES_MENU"]:
                self.client_state = "LOBBY_MENU"
            else:
                super().handle_back_button(current_state)

    def scan_downloaded_games(self):
        """Scans the user's download directory to find owned games."""
        logging.info(f"Scanning for downloaded games for user {self.username}...")
        self.my_games = [] # Reset
        if not self.username:
            return
            
        user_download_dir = os.path.join("player", "downloads", self.username)
        if not os.path.exists(user_download_dir):
            return
        
        # Scan for .py files
        downloaded_files = {}
        for filename in os.listdir(user_download_dir):
            if filename.endswith('.py'):
                # Extract game name from filename (remove .py extension)
                game_name = filename[:-3]
                file_path = os.path.join(user_download_dir, filename)
                downloaded_files[game_name] = file_path
        
        # Match with games from server to get full metadata
        for game in self.all_games:
            game_name = game.get("name", "")
            game_id = game.get("id")
            if game_name in downloaded_files:
                # Game is downloaded - check if we have version info
                if game_id and game_id not in self.downloaded_versions:
                    # Initialize version info if missing (for games downloaded before version tracking)
                    self.downloaded_versions[game_id] = {
                        "version": game.get("current_version", "1"),
                        "downloaded_at": os.path.getmtime(downloaded_files[game_name])
                    }
                
                # Game is downloaded
                game_data = {
                    "id": game_id,
                    "name": game.get("name"),
                    "current_version": game.get("current_version", "1"),
                    "description": game.get("description", ""),
                    "author": game.get("author", "")
                }
                # Mark update available if needed
                if self._is_update_available(game_id):
                    game_data["update_available"] = True
                self.my_games.append(game_data)
        
        # Also include any downloaded games not in server list (orphaned)
        for game_name, file_path in downloaded_files.items():
            if not any(g.get("name") == game_name for g in self.my_games):
                self.my_games.append({
                    "id": None,
                    "name": game_name,
                    "current_version": "unknown",
                    "description": "Downloaded game (not in server list)",
                    "author": "unknown"
                })
        
        # Update create room buttons
        self._update_create_room_buttons()
    
    def _is_game_downloaded(self, game_id):
        """Check if a game is already downloaded."""
        for game in self.my_games:
            if game.get("id") == game_id:
                return True
        return False
    
    def _is_update_available(self, game_id):
        """Check if an update is available for a downloaded game."""
        if game_id not in self.downloaded_versions:
            return False
        
        # Find the game in all_games to get server version
        for game in self.all_games:
            if game.get("id") == game_id:
                server_version = game.get("current_version")
                local_version = self.downloaded_versions[game_id].get("version")
                if local_version and server_version and server_version != local_version:
                    return True
                break
        return False
    
    def _compare_versions(self, games):
        """Compare server versions with local versions and mark updates."""
        for game in games:
            game_id = game.get("id")
            if game_id in self.downloaded_versions:
                server_version = game.get("current_version")
                local_version = self.downloaded_versions[game_id].get("version")
                if local_version and server_version and server_version != local_version:
                    # Mark as update available
                    game["update_available"] = True
                    logging.info(f"Update available for game {game_id}: local={local_version}, server={server_version}")
                else:
                    game["update_available"] = False
    
    def _get_game_name(self, game_id):
        """Get game name by ID."""
        for game in self.all_games + self.my_games:
            if game.get("id") == game_id:
                return game.get("name", f"Game {game_id}")
        return f"Game {game_id}"
    
    def _update_create_room_buttons(self):
        """Update create room buttons for downloaded games."""
        self.create_room_buttons = {}
        # Buttons will be created dynamically in draw_my_games_menu
            
    def draw_lobby_menu(self, screen):
        self.ui_elements["store_btn"].draw(screen)
        self.ui_elements["my_games_btn"].draw(screen)
        draw_text(screen, "Game Rooms", 50, 100, self.fonts["TITLE"], (255, 255, 255))
        
        # Request rooms list periodically
        current_time = time.time()
        if not hasattr(self, 'last_rooms_refresh'):
            self.last_rooms_refresh = 0
        if current_time - self.last_rooms_refresh > 3:  # Refresh every 3 seconds
            send_to_lobby_queue({"action": "list_rooms"})
            self.last_rooms_refresh = current_time
        
        # Draw public rooms
        if not self.game_rooms:
            draw_text(screen, "No rooms available.", 50, 180, self.fonts["MEDIUM"], (200, 200, 200))
        else:
            # Headers
            draw_text(screen, "Room Name", 50, 150, self.fonts["TINY"], (200, 200, 200))
            draw_text(screen, "Game", 300, 150, self.fonts["TINY"], (200, 200, 200))
            draw_text(screen, "Players", 500, 150, self.fonts["TINY"], (200, 200, 200))
            draw_text(screen, "Action", 650, 150, self.fonts["TINY"], (200, 200, 200))
            
            self.room_join_buttons = {}
            for i, room in enumerate(self.game_rooms):
                y_pos = 180 + i * 40
                room_id = room.get("id")
                room_name = room.get("name", "Unknown")
                game_name = room.get("game_name", "Unknown")
                players_count = room.get("players", 0)
                
                # Only show rooms that aren't full
                if players_count < 2:
                    draw_text(screen, room_name, 50, y_pos, self.fonts["SMALL"], (255, 255, 255))
                    draw_text(screen, game_name, 300, y_pos, self.fonts["SMALL"], (255, 255, 255))
                    draw_text(screen, f"{players_count}/2", 500, y_pos, self.fonts["SMALL"], (255, 255, 255))
                    
                    # Join button
                    if room_id not in self.room_join_buttons:
                        self.room_join_buttons[room_id] = Button(650, y_pos - 5, 100, 30, self.fonts["SMALL"], "Join")
                    btn = self.room_join_buttons[room_id]
                    btn.draw(screen)
        
    def _draw_game_table(self, screen, games, title, show_download_btn=False, show_create_room_btn=False):
        """Helper to draw a table of games."""
        draw_text(screen, title, 350, 50, self.fonts["TITLE"], (255, 255, 255))
        
        # Headers - use TINY font (smaller than content)
        draw_text(screen, "Name", 50, 150, self.fonts["TINY"], (200, 200, 200))
        draw_text(screen, "Description", 500, 150, self.fonts["TINY"], (200, 200, 200))
        if show_download_btn or show_create_room_btn:
            draw_text(screen, "Action", 750, 150, self.fonts["TINY"], (200, 200, 200))

        if not games:
            draw_text(screen, "No games to display.", 50, 220, self.fonts["MEDIUM"], (200, 200, 200))
            logging.debug(f"_draw_game_table: No games to display for {title}")
            return
        
        logging.debug(f"_draw_game_table: Drawing {len(games)} games for {title}")
            
        for i, game in enumerate(games):
            y_pos = 200 + i * 40
            game_id = game.get('id')
            game_name = str(game.get('name', 'N/A'))
            version = str(game.get('current_version', 'N/A'))
            
            # Combine game name with version
            game_name_with_version = f"{game_name} v{version}"
            draw_text(screen, game_name_with_version, 50, y_pos, self.fonts["SMALL"], (255, 255, 255))
            
            # Truncate long descriptions
            desc = str(game.get('description', 'N/A'))
            if len(desc) > 30:
                desc = desc[:27] + "..."
            draw_text(screen, desc, 500, y_pos, self.fonts["SMALL"], (255, 255, 255))
            
            # Download button for store
            if show_download_btn and game_id:
                if game_id not in self.download_buttons:
                    # Determine initial button text
                    if self._is_update_available(game_id):
                        btn_text = "Update"
                    elif self._is_game_downloaded(game_id):
                        btn_text = "Downloaded"
                    else:
                        btn_text = "Download"
                    self.download_buttons[game_id] = Button(750, y_pos - 5, 100, 30, self.fonts["SMALL"], btn_text)
                btn = self.download_buttons[game_id]
                # Update button text based on current state
                if self._is_update_available(game_id):
                    btn.text = "Update"
                elif self._is_game_downloaded(game_id):
                    btn.text = "Downloaded"
                else:
                    btn.text = "Download"
                btn.draw(screen)
                
                # Show visual indicator for update available (draw a small badge or different color)
                if self._is_update_available(game_id):
                    # Draw a small indicator next to version number
                    draw_text(screen, "!", 330, y_pos, self.fonts["SMALL"], (255, 200, 0))  # Yellow exclamation mark
            
            # Create room button for my games
            if show_create_room_btn and game_id:
                if game_id not in self.create_room_buttons:
                    # "New Room" button with smaller font
                    self.create_room_buttons[game_id] = Button(750, y_pos - 5, 80, 30, self.fonts["TINY"], "New Room")
                    # Private/Public toggle button
                    self.room_toggle_buttons[game_id] = Button(840, y_pos - 5, 60, 30, self.fonts["TINY"], "Public")
                btn = self.create_room_buttons[game_id]
                btn.draw(screen)
                # Draw toggle button
                toggle_btn = self.room_toggle_buttons.get(game_id)
                if toggle_btn:
                    # Update button text based on state
                    toggle_btn.text = "Public" if self.room_is_public else "Private"
                    toggle_btn.draw(screen)

    def draw_store_menu(self, screen):
        logging.debug(f"draw_store_menu: all_games has {len(self.all_games)} games")
        self._draw_game_table(screen, self.all_games, "Game Store", show_download_btn=True)
        
    def draw_my_games_menu(self, screen):
        logging.debug(f"draw_my_games_menu: my_games has {len(self.my_games)} games")
        self._draw_game_table(screen, self.my_games, "My Games", show_create_room_btn=True)
    
    def draw_room_waiting_screen(self, screen):
        """Draw the room waiting screen - shows room status and allows invitations."""
        if not self.current_room_data:
            draw_text(screen, "Loading room...", 350, 300, self.fonts["MEDIUM"], (255, 255, 255))
            return
        
        room_name = self.current_room_data.get("name", "Unknown Room")
        game_name = self.current_room_data.get("game_name", "Unknown Game")
        players = self.current_room_data.get("players", [])
        host = self.current_room_data.get("host")
        is_public = self.current_room_data.get("is_public", True)
        room_type = "Public" if is_public else "Private"
        room_status = self.current_room_data.get("status", "idle")
        
        # Room title
        draw_text(screen, f"{room_name}", 50, 50, self.fonts["MEDIUM"], (255, 255, 255))
        draw_text(screen, f"Game: {game_name}", 50, 90, self.fonts["MEDIUM"], (200, 200, 200))
        draw_text(screen, f"Type: {room_type}", 50, 120, self.fonts["SMALL"], (150, 150, 150))
        
        # Show game status if playing
        if room_status == "playing":
            draw_text(screen, "Game in Progress", 50, 150, self.fonts["MEDIUM"], (0, 255, 0))
        
        # Players section
        draw_text(screen, "Players:", 50, 190, self.fonts["MEDIUM"], (255, 255, 255))
        for i, player in enumerate(players):
            y_pos = 230 + i * 40
            player_text = f"P{i+1}: {player}"
            if player == host:
                player_text += " (Host)"
            draw_text(screen, player_text, 50, y_pos, self.fonts["SMALL"], (255, 255, 255))
        
        # Show waiting message if not full and not playing
        if room_status != "playing":
            if len(players) < 2:
                draw_text(screen, f"Waiting for {2 - len(players)} more player(s)...", 50, 310, self.fonts["SMALL"], (200, 200, 200))
                
                # Online users list for invitations
                draw_text(screen, "Invite Players:", 450, 190, self.fonts["MEDIUM"], (255, 255, 255))
                
                # Initialize invite_buttons if not exists
                if not hasattr(self, 'invite_buttons'):
                    self.invite_buttons = {}
                
                # Request users list if we don't have it or it's empty (only once per refresh)
                if not self.online_users:
                    current_time = time.time()
                    if not hasattr(self, 'last_users_request') or current_time - getattr(self, 'last_users_request', 0) > 2:
                        send_to_lobby_queue({"action": "list_users"})
                        self.last_users_request = current_time
                    draw_text(screen, "Loading users...", 450, 230, self.fonts["SMALL"], (150, 150, 150))
                else:
                    # Filter out users already in the room
                    available_users = [u for u in self.online_users if u.get("username") not in players]
                    
                    if not available_users:
                        draw_text(screen, "No other users available.", 450, 230, self.fonts["SMALL"], (150, 150, 150))
                    else:
                        # Draw online users with invite buttons
                        for i, user in enumerate(available_users):
                            y_pos = 230 + i * 40
                            username = user.get("username", "Unknown")
                            
                            # Create invite button for each user (reuse if exists)
                            if username not in self.invite_buttons:
                                self.invite_buttons[username] = Button(450, y_pos - 5, 200, 35, self.fonts["SMALL"], f"Invite {username}")
                            btn = self.invite_buttons[username]
                            # Update button position in case list changed
                            btn.rect.y = y_pos - 5
                            btn.draw(screen)
                            
                            # Show user status
                            status = user.get("status", "unknown")
                            draw_text(screen, f"({status})", 660, y_pos, self.fonts["TINY"], (150, 150, 150))
            else:
                # Room is full
                draw_text(screen, "Room is full!", 50, 310, self.fonts["MEDIUM"], (0, 255, 0))
                if host == self.username:
                    # Host can start the game
                    if not hasattr(self, 'start_game_btn'):
                        self.start_game_btn = Button(50, 350, 200, 40, self.fonts["MEDIUM"], "Start Game")
                    self.start_game_btn.draw(screen)
                else:
                    draw_text(screen, "Waiting for host to start...", 50, 350, self.fonts["SMALL"], (200, 200, 200))
        else:
            # Game is playing
            draw_text(screen, "Game is running...", 50, 310, self.fonts["MEDIUM"], (0, 255, 0))
            draw_text(screen, "Room remains open until game ends", 50, 350, self.fonts["SMALL"], (150, 150, 150))
    
    def draw_invite_popup(self, screen):
        """Draws the invitation popup overlay."""
        if not self.pending_invite:
            return
        
        # Semi-transparent overlay
        overlay = pygame.Surface((BASE_CONFIG["SCREEN"]["WIDTH"], BASE_CONFIG["SCREEN"]["HEIGHT"]))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        
        # Popup box
        popup_rect = pygame.Rect(200, 250, 500, 200)
        pygame.draw.rect(screen, (40, 40, 50), popup_rect, 0, border_radius=10)
        pygame.draw.rect(screen, (255, 255, 255), popup_rect, 2, border_radius=10)
        
        # Invitation text
        from_user = self.pending_invite.get("from_user", "Unknown")
        game_name = self.pending_invite.get("game_name", "Unknown Game")
        inv_text = f"{from_user} invited you to play {game_name}!"
        
        # Wrap text if needed
        words = inv_text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if self.fonts["MEDIUM"].size(test_line)[0] < 460:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Draw text lines
        y_offset = 280
        for line in lines:
            draw_text(screen, line, 230, y_offset, self.fonts["MEDIUM"], (255, 255, 255))
            y_offset += 30
        
        # Draw buttons
        if self.invite_accept_btn:
            self.invite_accept_btn.draw(screen)
        if self.invite_decline_btn:
            self.invite_decline_btn.draw(screen)

    def _attempt_registration(self):
        # Players should not register as developers
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            send_to_lobby_queue({
                "action": "register",
                "data": {"user": user, "pass": password, "is_developer": False}
            })
            with self.state_lock:
                self.error_message = None



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Player Client")
    parser.add_argument('-c', '--client', type=int, choices=[1, 2, 3], 
                       help='Auto-login as player 1, 2, or 3')
    args = parser.parse_args()
    
    auto_login = None
    if args.client:
        if args.client in PLAYER_USERS:
            auto_login = PLAYER_USERS[args.client]
            logging.info(f"Auto-login enabled for player {args.client}: {auto_login['user']}")
        else:
            logging.warning(f"Invalid client number: {args.client}")
    
    client = PlayerGUI(auto_login_user=auto_login)
    client.run()
