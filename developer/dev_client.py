# developer/dev_client.py

import sys
import os
import argparse
import time
import threading
import logging
import pygame

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Go up one level
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
from gui.base_gui import BaseGUI, draw_text, Button, TextInput
from gui.base_gui import BASE_CONFIG
from client.shared import send_to_lobby_queue

# Predefined developer user for auto-login
DEVELOPER_USER = {"user": "dev", "pass": "dev123"}

class DeveloperGUI(BaseGUI):
    def __init__(self, auto_login=False):
        super().__init__(title="Developer Client")
        self.is_developer = False
        self.my_games = []
        self.auto_login = auto_login  # Flag for auto-login
        self.auto_login_sent = False  # Track if auto-login has been sent
        self.success_message = None  # Success message for upload
        self.upload_focused_element_idx = 0  # Track focused element on upload screen

    # Override methods for developer-specific functionality
    def draw_custom_state(self, screen, state):
        # In the future, this will handle GAME_LIST, CREATE_GAME, etc.
        draw_text(screen, f"Developer State: {state}", 100, 100, self.fonts["MEDIUM"], (255, 255, 255))

    def handle_custom_events(self, event, state):
        # Handle events for GAME_LIST, etc.
        pass

    def handle_network_message(self, msg):
        # Override to check for developer status
        status = msg.get("status")
        reason = msg.get("reason")

        if status == "ok" and reason == "login_successful":
            user_data = msg.get("user", {})
            self.is_developer = user_data.get("is_developer", False)
            
            with self.state_lock:
                if self.is_developer:
                    self.client_state = "MY_GAMES_MENU"
                    send_to_lobby_queue({"action": "list_my_games"})
                    self.error_message = None
                else:
                    self.client_state = "ERROR"
                    self.error_message = "User is not a developer"
        
        elif status == "ok" and reason == "game_uploaded":
            # Game upload successful
            game_id = msg.get('game_id')
            version = msg.get('version')
            logging.info(f"Game uploaded successfully: game_id={game_id}, version={version}")
            # Show success message and go back to games menu
            with self.state_lock:
                self.success_message = f"Game uploaded! ID: {game_id}, Version: {version}"
                self.error_message = None
                self.client_state = "MY_GAMES_MENU"
                # Clear the form
                self.ui_elements["game_name_input"].text = ""
                self.ui_elements["game_desc_input"].text = ""
                self.ui_elements["game_version_input"].text = "1"
                self.ui_elements["file_path_input"].text = "developer/games/"
            # Refresh games list
            send_to_lobby_queue({"action": "list_my_games"})
        
        elif status == "error":
            # Handle errors - don't automatically logout unless it's a critical auth error
            error_reason = reason
            logging.warning(f"Received error: {error_reason}")
            
            if error_reason == "not_developer":
                # Developer check failed - this shouldn't happen if we're logged in as developer
                # But handle it gracefully without logging out
                logging.warning("Received 'not_developer' error - may indicate session issue")
                with self.state_lock:
                    # Show error but don't logout - might be a temporary DB issue
                    self.error_message = f"Developer check failed: {error_reason}. Your session may have expired. Please try again."
                    # Don't change state - stay in current state
            elif error_reason in ["must_be_logged_in", "session_expired", "not_logged_in", "already_logged_in"]:
                # Critical auth errors - need to logout
                with self.state_lock:
                    self.error_message = f"Authentication error: {error_reason}"
                    self.client_state = "LOGIN"
                    self.username = None
                    self.is_developer = False
                    # Close socket to force reconnection
                    if self.lobby_socket:
                        try:
                            self.lobby_socket.close()
                        except:
                            pass
                        self.lobby_socket = None
            else:
                # Other errors - show error but don't logout
                with self.state_lock:
                    self.error_message = f"Error: {error_reason}"
                    # Don't change state - stay in current state
        
        elif msg.get("games"):
            self.my_games = msg.get("games", [])

        else:
            # Fallback to base handling for other messages (like errors)
            super().handle_network_message(msg)

    def _attempt_registration(self):
        """Overrides base method to register a user as a developer."""
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            # Assumes the server can handle an 'is_developer' flag
            send_to_lobby_queue({
                "action": "register",
                "data": {
                    "user": user, 
                    "pass": password,
                    "is_developer": True 
                }
            })
            with self.state_lock:
                self.error_message = None

    def _start_network_thread(self):
        super()._start_network_thread()
        
        # If auto-login is enabled, wait for connection and send login
        if self.auto_login:
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
                    logging.info(f"Auto-login as developer: {DEVELOPER_USER['user']}")
                    send_to_lobby_queue({
                        "action": "login",
                        "data": {"user": DEVELOPER_USER["user"], "pass": DEVELOPER_USER["pass"]}
                    })
                    self.username = DEVELOPER_USER["user"]
                else:
                    logging.warning("Could not establish connection for auto-login")
            
            threading.Thread(target=auto_login_thread, daemon=True).start()

    def _create_ui_elements(self):
        super()._create_ui_elements()
        self.ui_elements["add_game_btn"] = Button(10, 10, 150, 40, self.fonts["SMALL"], "Add Game")
        
        # UI elements for the upload screen
        self.ui_elements["game_name_input"] = TextInput(300, 200, 400, 32, self.fonts["SMALL"])
        self.ui_elements["game_desc_input"] = TextInput(300, 250, 400, 90, self.fonts["TINY"], multiline=True) # Larger height, multiline, smaller font
        self.ui_elements["game_version_input"] = TextInput(300, 350, 200, 32, self.fonts["SMALL"], "1") # Adjust Y for description field
        # Pre-fill with developer/games/ path (relative from project root)
        self.ui_elements["file_path_input"] = TextInput(300, 400, 400, 32, self.fonts["SMALL"], "developer/games/") # File path input
        self.ui_elements["upload_btn"] = Button(350, 450, 200, 50, self.fonts["MEDIUM"], "Upload")
        
        # List of focusable elements on upload screen (in tab order)
        self.ui_elements["upload_focusable_elements"] = [
            "game_name_input",
            "game_desc_input", 
            "game_version_input",
            "file_path_input",
            "upload_btn"
        ]
        self.error_message_timer = 0

    def draw_custom_state(self, screen, state):
        if state == "MY_GAMES_MENU":
            self.draw_my_games_menu(screen)
        elif state == "UPLOAD_GAME":
            self.draw_upload_game_screen(screen)

    def handle_custom_events(self, event, state):
        if state == "MY_GAMES_MENU":
            if self.ui_elements["add_game_btn"].handle_event(event):
                with self.state_lock:
                    self.client_state = "UPLOAD_GAME"
                    # Initialize focus on first element when entering upload screen
                    self.upload_focused_element_idx = 0
                    self.ui_elements["game_name_input"].active = True
                    self.ui_elements["game_name_input"].color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"]
                    # Deactivate other inputs
                    for name in ["game_desc_input", "game_version_input", "file_path_input"]:
                        self.ui_elements[name].active = False
                        self.ui_elements[name].color = BASE_CONFIG["COLORS"]["INPUT_BOX"]
                    self.ui_elements["upload_btn"].is_focused = False
            # Handle update/delete buttons here in the future
        
        elif state == "UPLOAD_GAME":
            self.handle_upload_game_events(event)

    def handle_upload_game_events(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                # Tab navigation - cycle through focusable elements
                current_focus_name = self.ui_elements["upload_focusable_elements"][self.upload_focused_element_idx]
                
                # Deactivate current element
                if current_focus_name in ["game_name_input", "game_desc_input", "game_version_input", "file_path_input"]:
                    self.ui_elements[current_focus_name].active = False
                    self.ui_elements[current_focus_name].color = BASE_CONFIG["COLORS"]["INPUT_BOX"]
                elif current_focus_name == "upload_btn":
                    self.ui_elements[current_focus_name].is_focused = False
                
                # Move to next element
                self.upload_focused_element_idx = (self.upload_focused_element_idx + 1) % len(self.ui_elements["upload_focusable_elements"])
                new_focus_name = self.ui_elements["upload_focusable_elements"][self.upload_focused_element_idx]
                
                # Activate new element
                if new_focus_name in ["game_name_input", "game_desc_input", "game_version_input", "file_path_input"]:
                    self.ui_elements[new_focus_name].active = True
                    self.ui_elements[new_focus_name].color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"]
                elif new_focus_name == "upload_btn":
                    self.ui_elements[new_focus_name].is_focused = True
            elif event.key == pygame.K_RETURN:
                # Enter key - trigger upload if button is focused, otherwise submit current input
                focused_name = self.ui_elements["upload_focusable_elements"][self.upload_focused_element_idx]
                if focused_name == "upload_btn":
                    self._attempt_upload_game()
                else:
                    # If an input is focused, just let it handle the event normally
                    for name in ["game_name_input", "game_desc_input", "game_version_input", "file_path_input"]:
                        if self.ui_elements[name].active:
                            self.ui_elements[name].handle_event(event)
            else:
                # Pass other key events to active input fields
                for name in ["game_name_input", "game_desc_input", "game_version_input", "file_path_input"]:
                    self.ui_elements[name].handle_event(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Handle mouse clicks - update focus based on what was clicked
            clicked_input = None
            for name in ["game_name_input", "game_desc_input", "game_version_input", "file_path_input"]:
                if self.ui_elements[name].handle_event(event):
                    clicked_input = name
                    # Update focused index
                    if name in self.ui_elements["upload_focusable_elements"]:
                        self.upload_focused_element_idx = self.ui_elements["upload_focusable_elements"].index(name)
            
            # Handle button click
            if self.ui_elements["upload_btn"].handle_event(event):
                self._attempt_upload_game()
                # Update focused index to button
                self.upload_focused_element_idx = self.ui_elements["upload_focusable_elements"].index("upload_btn")
    
    def draw_my_games_menu(self, screen):
        draw_text(screen, "My Games", 350, 50, self.fonts["TITLE"], (255, 255, 255))
        self.ui_elements["add_game_btn"].draw(screen)

        # Headers
        draw_text(screen, "ID", 50, 150, self.fonts["MEDIUM"], (200, 200, 200))
        draw_text(screen, "Name", 150, 150, self.fonts["MEDIUM"], (200, 200, 200))
        draw_text(screen, "Version", 450, 150, self.fonts["MEDIUM"], (200, 200, 200))

        for i, game in enumerate(self.my_games):
            y_pos = 200 + i * 50
            draw_text(screen, str(game.get('id')), 50, y_pos, self.fonts["SMALL"], (255, 255, 255))
            draw_text(screen, game.get('name'), 150, y_pos, self.fonts["SMALL"], (255, 255, 255))
            draw_text(screen, game.get('current_version'), 450, y_pos, self.fonts["SMALL"], (255, 255, 255))

            # Placeholder buttons (adjusted width and position)
            update_btn = Button(580, y_pos - 5, 100, 30, self.fonts["TINY"], "Update")
            delete_btn = Button(690, y_pos - 5, 100, 30, self.fonts["TINY"], "Delete")
            update_btn.draw(screen)
            delete_btn.draw(screen)

    def draw_upload_game_screen(self, screen):
        draw_text(screen, "Upload New Game", 300, 100, self.fonts["TITLE"], (255, 255, 255))
        
        # Draw labels and input boxes
        draw_text(screen, "Name:", 100, 200, self.fonts["SMALL"], (255, 255, 255))
        self.ui_elements["game_name_input"].draw(screen)
        
        draw_text(screen, "Description:", 100, 250, self.fonts["SMALL"], (255, 255, 255))
        self.ui_elements["game_desc_input"].draw(screen)
        
        draw_text(screen, "Version:", 100, 350, self.fonts["SMALL"], (255, 255, 255))
        self.ui_elements["game_version_input"].draw(screen)
        
        draw_text(screen, "File Path:", 100, 400, self.fonts["SMALL"], (255, 255, 255))
        self.ui_elements["file_path_input"].draw(screen)
        draw_text(screen, "(pre-filled with developer/games/ - just add filename, e.g., tetris.py)", 100, 435, self.fonts["TINY"], (150, 150, 150))
        
        self.ui_elements["upload_btn"].draw(screen)

        # Handle timed error message
        if self.error_message and self.error_message_timer > 0:
            if time.time() > self.error_message_timer:
                self.error_message = None
                self.error_message_timer = 0
            else:
                # Use SMALL font and wrap long messages
                error_text = self.error_message
                if len(error_text) > 60:  # Truncate very long messages
                    error_text = error_text[:57] + "..."
                draw_text(screen, error_text, 50, 520, self.fonts["SMALL"], (255, 50, 50))
        elif self.error_message:
            # Show error message if no timer (persistent errors) - use SMALL font
            error_text = self.error_message
            if len(error_text) > 60:  # Truncate very long messages
                error_text = error_text[:57] + "..."
            draw_text(screen, error_text, 50, 520, self.fonts["SMALL"], (255, 50, 50))
        
        # Show success message if present (with auto-clear after 3 seconds)
        if hasattr(self, 'success_message') and self.success_message:
            if not hasattr(self, 'success_message_timer'):
                self.success_message_timer = time.time() + 3
            if time.time() < self.success_message_timer:
                draw_text(screen, self.success_message, 300, 500, self.fonts["SMALL"], (50, 255, 50))
            else:
                self.success_message = None
                self.success_message_timer = None

    def _resolve_file_path(self, file_path_str: str) -> str | None:
        """
        Resolves a file path string to an absolute path.
        Handles:
        - Absolute paths (e.g., /home/user/game.py)
        - Relative paths from project root (e.g., developer/games/tetris.py)
        - Filenames only (assumes developer/games/ folder)
        Returns None if file doesn't exist.
        """
        if not file_path_str or not file_path_str.strip():
            return None
        
        file_path_str = file_path_str.strip()
        
        # If it's already an absolute path, use it directly
        if os.path.isabs(file_path_str):
            if os.path.exists(file_path_str):
                return file_path_str
            return None
        
        # Try as relative path from project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        relative_path = os.path.join(project_root, file_path_str)
        if os.path.exists(relative_path):
            return relative_path
        
        # Try as filename in developer/games/ folder
        developer_games_path = os.path.join(project_root, "developer", "games", file_path_str)
        if os.path.exists(developer_games_path):
            return developer_games_path
        
        # File not found
        return None
            
    def _attempt_upload_game(self):
        """Prepares and sends the upload_game request."""
        import base64
        
        name = self.ui_elements["game_name_input"].text
        version = self.ui_elements["game_version_input"].text
        file_path_str = self.ui_elements["file_path_input"].text
        
        if not name or not version or not file_path_str:
            self.error_message = "Missing fields (name, version, or file path)"
            self.error_message_timer = time.time() + 2
            return
        
        # Resolve the file path
        file_path = self._resolve_file_path(file_path_str)
        if not file_path:
            self.error_message = f"File not found: {file_path_str}"
            self.error_message_timer = time.time() + 3
            return
            
        try:
            # Read the file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Encode to base64
            file_data_b64 = base64.b64encode(file_data).decode('utf-8')
            
            # Send upload request
            send_to_lobby_queue({
                "action": "upload_game",
                "data": {
                    "name": name,
                    "description": self.ui_elements["game_desc_input"].text,
                    "version": version,
                    "file_data": file_data_b64
                }
            })
            
            # Stay on upload screen - wait for server response
            # Don't change state yet - let handle_network_message handle the response
            # Clear error message
            with self.state_lock:
                self.error_message = None
                self.error_message_timer = 0

        except Exception as e:
            self.error_message = f"Error: {e}"
            self.error_message_timer = time.time() + 3 # Show error for longer

    def handle_back_button(self, current_state):
        """Custom back button behavior for the developer client."""
        with self.state_lock:
            if current_state == "UPLOAD_GAME":
                self.client_state = "MY_GAMES_MENU"
                # Clear fields (but keep the default path prefix)
                self.ui_elements["game_name_input"].text = ""
                self.ui_elements["game_desc_input"].text = ""
                self.ui_elements["game_version_input"].text = "1" # Only one number is simpler to keep track of and debug
                self.ui_elements["file_path_input"].text = "developer/games/"
                self.error_message = None
                self.success_message = None
            else:
                # Default behavior for MY_GAMES_MENU or other states - logout
                self.client_state = "LOGIN"
                self.username = None
                self.error_message = None
                self.is_developer = False # Also reset developer status
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Developer Client")
    parser.add_argument('-c', '--client', type=int, choices=[1], default=None,
                       help='Auto-login as developer (use -c 1)')
    args = parser.parse_args()
    
    auto_login = args.client == 1
    if auto_login:
        logging.info("Auto-login enabled for developer")
    
    client = DeveloperGUI(auto_login=auto_login)
    client.run()
