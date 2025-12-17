# developer/dev_client.py

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Go up one level
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
from gui.base_gui import BaseGUI, draw_text, Button, TextInput
from client.shared import send_to_lobby_queue

class DeveloperGUI(BaseGUI):
    def __init__(self):
        super().__init__(title="Developer Client")
        self.is_developer = False
        self.my_games = []

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

    def _create_ui_elements(self):
        super()._create_ui_elements()
        self.ui_elements["add_game_btn"] = Button(10, 10, 150, 40, self.fonts["SMALL"], "Add Game")
        
        # UI elements for the upload screen
        self.ui_elements["game_name_input"] = TextInput(300, 200, 400, 32, self.fonts["SMALL"])
        self.ui_elements["game_desc_input"] = TextInput(300, 250, 400, 90, self.fonts["TINY"], multiline=True) # Larger height, multiline, smaller font
        self.ui_elements["game_version_input"] = TextInput(300, 350, 200, 32, self.fonts["SMALL"], "1") # Adjust Y for description field
        self.ui_elements["select_file_btn"] = Button(300, 400, 200, 40, self.fonts["SMALL"], "Select File") 
        self.ui_elements["upload_btn"] = Button(350, 450, 200, 50, self.fonts["MEDIUM"], "Upload")
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
            # Handle update/delete buttons here in the future
        
        elif state == "UPLOAD_GAME":
            self.handle_upload_game_events(event)

    def handle_upload_game_events(self, event):
        self.ui_elements["game_name_input"].handle_event(event)
        self.ui_elements["game_desc_input"].handle_event(event)
        self.ui_elements["game_version_input"].handle_event(event)
        
        if self.ui_elements["select_file_btn"].handle_event(event):
            self._select_game_file()
        
        if self.ui_elements["upload_btn"].handle_event(event):
            self._attempt_upload_game()
    
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
        
        draw_text(screen, "File:", 100, 400, self.fonts["SMALL"], (255, 255, 255))
        self.ui_elements["select_file_btn"].draw(screen)

        # Show selected file name
        selected_file_text = self.ui_elements.get("selected_file_name", "No file selected")
        draw_text(screen, selected_file_text, 520, 410, self.fonts["TINY"], (200, 200, 200))
        
        self.ui_elements["upload_btn"].draw(screen)

        # Handle timed error message
        if self.error_message and self.error_message_timer > 0:
            if time.time() > self.error_message_timer:
                self.error_message = None
                self.error_message_timer = 0
            else:
                draw_text(screen, self.error_message, 300, 520, self.fonts["MEDIUM"], (255, 50, 50))

    def _select_game_file(self):
        """Opens a file dialog to select a game file."""
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw() # Hide the main window
        file_path = filedialog.askopenfilename(
            title="Select Game File",
            initialdir="developer/games", # Start in the local games folder
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        root.destroy()
        
        if file_path:
            self.ui_elements["selected_file_path"] = file_path
            self.ui_elements["selected_file_name"] = os.path.basename(file_path)
            
    def _attempt_upload_game(self):
        """Prepares and sends the upload_game request."""
        import base64
        
        name = self.ui_elements["game_name_input"].text
        version = self.ui_elements["game_version_input"].text
        file_path = self.ui_elements.get("selected_file_path")
        
        if not all([name, version, file_path]):
            self.error_message = "Missing fields"
            self.error_message_timer = time.time() + 1 # Show for 1 second
            return
            
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            file_data_b64 = base64.b64encode(file_data).decode('utf-8')
            
            send_to_lobby_queue({
                "action": "upload_game",
                "data": {
                    "name": name,
                    "description": self.ui_elements["game_desc_input"].text,
                    "version": version,
                    "file_data": file_data_b64
                }
            })
            # Go back to the dev menu after attempting upload
            with self.state_lock:
                self.client_state = "MY_GAMES_MENU"
                self.success_message = "Upload request sent..." # Optimistic feedback
                # Refresh the games list
                send_to_lobby_queue({"action": "list_my_games"})

        except Exception as e:
            self.error_message = f"Error: {e}"
            self.error_message_timer = time.time() + 3 # Show error for longer

    def handle_back_button(self, current_state):
        """Custom back button behavior for the developer client."""
        with self.state_lock:
            if current_state == "UPLOAD_GAME":
                self.client_state = "MY_GAMES_MENU"
                # Clear fields
                self.ui_elements["game_name_input"].text = ""
                self.ui_elements["game_desc_input"].text = ""
                self.ui_elements["game_version_input"].text = "1.0.0"
                self.ui_elements["selected_file_path"] = None
                self.ui_elements["selected_file_name"] = "No file selected"
                # Clear any error/success messages
                self.error_message = None
                self.success_message = None
            else:
                # Default behavior for MY_GAMES_MENU or other states
                self.client_state = "LOGIN"
                self.username = None
                self.error_message = None
                self.is_developer = False # Also reset developer status
if __name__ == "__main__":
    client = DeveloperGUI()
    client.run()
