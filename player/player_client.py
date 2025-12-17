# player/player_client.py

import sys
import os
import logging
import base64
import argparse
import time
import threading

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Go up one level
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.base_gui import BaseGUI, draw_text, Button, TextInput, BASE_CONFIG
from client.shared import send_to_lobby_queue

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
        elif state == "ROOM_CREATE":
            self.draw_room_create_screen(screen)

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
                    # Request online users list and show room creation screen
                    send_to_lobby_queue({"action": "list_users"})
                    self.current_room_game_id = game_id
                    with self.state_lock:
                        self.client_state = "ROOM_CREATE"
                    logging.info(f"Preparing to create room for game {game_id}")
            
            # Handle private/public toggle button clicks
            for game_id, toggle_btn in self.room_toggle_buttons.items():
                if toggle_btn.handle_event(event):
                    # Toggle room privacy state
                    self.room_is_public = not self.room_is_public
                    logging.info(f"Room privacy toggled to: {'Public' if self.room_is_public else 'Private'}")
        
        elif state == "ROOM_CREATE":
            # Handle invite button clicks
            for username, invite_btn in self.invite_buttons.items():
                if invite_btn.handle_event(event):
                    # Send invitation (will implement later)
                    logging.info(f"Inviting {username} to room")
                    # TODO: Send invite action to server
            
            # Handle create room final button
            if hasattr(self, 'create_room_final_btn') and self.create_room_final_btn.handle_event(event):
                # Create the room
                if hasattr(self, 'current_room_game_id') and self.current_room_game_id:
                    send_to_lobby_queue({
                        "action": "create_room",
                        "data": {
                            "game_id": self.current_room_game_id,
                            "is_public": self.room_is_public,
                            "name": f"{self.username}'s {self._get_game_name(self.current_room_game_id)} Room"
                        }
                    })
                    # Return to my games menu
                    with self.state_lock:
                        self.client_state = "MY_GAMES_MENU"

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
            # Request games list after login
            send_to_lobby_queue({"action": "list_games"})
        
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
            # Filter to only online users
            self.online_users = [u for u in users if u.get("status") == "online" and u.get("username") != self.username]
            logging.info(f"Received {len(self.online_users)} online users for invitations")
        
        elif status == "ok" and msg.get("action") == "download_game":
            # Game download response
            self._handle_game_download(msg)
        
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
            if current_state == "ROOM_CREATE":
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
        # Placeholder for room list
        draw_text(screen, "No rooms available.", 50, 180, self.fonts["MEDIUM"], (200, 200, 200))
        
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
    
    def draw_room_create_screen(self, screen):
        """Draw the room creation screen with online users list."""
        draw_text(screen, "Create Room", 350, 50, self.fonts["TITLE"], (255, 255, 255))
        
        # Show game name
        if hasattr(self, 'current_room_game_id') and self.current_room_game_id:
            game_name = self._get_game_name(self.current_room_game_id)
            draw_text(screen, f"Game: {game_name}", 50, 100, self.fonts["MEDIUM"], (255, 255, 255))
        else:
            draw_text(screen, "Game: Unknown", 50, 100, self.fonts["MEDIUM"], (255, 255, 255))
        
        # Show room type
        room_type = "Public" if self.room_is_public else "Private"
        draw_text(screen, f"Room Type: {room_type}", 50, 130, self.fonts["SMALL"], (200, 200, 200))
        
        # Online users list header
        draw_text(screen, "Online Users (Click to Invite):", 50, 180, self.fonts["MEDIUM"], (200, 200, 200))
        
        # Draw online users list
        self.invite_buttons = {}
        if not self.online_users:
            draw_text(screen, "No other users online.", 50, 220, self.fonts["SMALL"], (150, 150, 150))
        else:
            for i, user in enumerate(self.online_users):
                y_pos = 220 + i * 40
                username = user.get("username", "Unknown")
                status = user.get("status", "unknown")
                
                # Create invite button for each user
                if username not in self.invite_buttons:
                    self.invite_buttons[username] = Button(50, y_pos - 5, 300, 35, self.fonts["SMALL"], f"Invite {username}")
                btn = self.invite_buttons[username]
                btn.draw(screen)
                
                # Show user status
                draw_text(screen, f"({status})", 360, y_pos, self.fonts["TINY"], (150, 150, 150))
        
        # Create room button (without invitation for now)
        if not hasattr(self, 'create_room_final_btn'):
            self.create_room_final_btn = Button(50, 500, 200, 40, self.fonts["MEDIUM"], "Create Room")
        self.create_room_final_btn.draw(screen)

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
