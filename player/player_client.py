# player/player_client.py

import sys
import os
import logging

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Go up one level
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.base_gui import BaseGUI, draw_text


from gui.base_gui import BaseGUI, draw_text, Button, TextInput
from client.shared import send_to_lobby_queue
class PlayerGUI(BaseGUI):
    def __init__(self):
        super().__init__(title="Player Client")
        self.all_games = [] # Games available in the store
        self.my_games = []  # Games downloaded by the player
        self.game_rooms = [] # Available rooms in the lobby

    def _create_ui_elements(self):
        super()._create_ui_elements()
        self.ui_elements["store_btn"] = Button(10, 10, 150, 40, self.fonts["SMALL"], "Store")
        self.ui_elements["my_games_btn"] = Button(170, 10, 150, 40, self.fonts["SMALL"], "My Games")

    def draw_custom_state(self, screen, state):
        if state == "LOBBY_MENU":
            self.draw_lobby_menu(screen)
        elif state == "STORE_MENU":
            self.draw_store_menu(screen)
        elif state == "MY_GAMES_MENU":
            self.draw_my_games_menu(screen)

    def handle_custom_events(self, event, state):
        if state == "LOBBY_MENU":
            if self.ui_elements["store_btn"].handle_event(event):
                self.client_state = "STORE_MENU"
            if self.ui_elements["my_games_btn"].handle_event(event):
                self.scan_downloaded_games() # Rescan just in case
                self.client_state = "MY_GAMES_MENU"
        elif state == "STORE_MENU":
            # Handle game download clicks in the future
            pass
        elif state == "MY_GAMES_MENU":
            # Handle game launch clicks in the future
            pass

    def handle_network_message(self, msg):
        """Handles player-specific network messages."""
        msg_type = msg.get("type")

        if msg_type == "all_games_list":
            self.all_games = msg.get("games", [])
        
        elif msg.get("status") == "ok" and msg.get("reason") == "login_successful":
            with self.state_lock:
                self.client_state = "LOBBY_MENU"
                self.error_message = None
        
        else:
            super().handle_network_message(msg)

    def handle_back_button(self, current_state):
        """Custom back button behavior for the player client."""
        with self.state_lock:
            if current_state in ["STORE_MENU", "MY_GAMES_MENU"]:
                self.client_state = "LOBBY_MENU"
            else:
                super().handle_back_button(current_state)

    def scan_downloaded_games(self):
        """Scans the user's download directory to find owned games."""
        # Placeholder implementation
        logging.info(f"Scanning for downloaded games for user {self.username}...")
        self.my_games = [] # Reset
        if not self.username:
            return
            
        user_download_dir = os.path.join("player", "downloads", self.username)
        if not os.path.exists(user_download_dir):
            return
        
        # This is a simplified scan. A real implementation would read metadata files.
        for game_dir in os.listdir(user_download_dir):
            self.my_games.append({
                "name": f"Downloaded: {game_dir}",
                "current_version": "1.0.0", # Placeholder
                "description": "A locally stored game." # Placeholder
            })
            
    def draw_lobby_menu(self, screen):
        self.ui_elements["store_btn"].draw(screen)
        self.ui_elements["my_games_btn"].draw(screen)
        draw_text(screen, "Game Rooms", 50, 100, self.fonts["TITLE"], (255, 255, 255))
        # Placeholder for room list
        draw_text(screen, "No rooms available.", 50, 180, self.fonts["MEDIUM"], (200, 200, 200))
        
    def _draw_game_table(self, screen, games, title):
        """Helper to draw a table of games."""
        draw_text(screen, title, 350, 50, self.fonts["TITLE"], (255, 255, 255))
        
        # Headers
        draw_text(screen, "Name", 50, 150, self.fonts["MEDIUM"], (200, 200, 200))
        draw_text(screen, "Version", 350, 150, self.fonts["MEDIUM"], (200, 200, 200))
        draw_text(screen, "Description", 500, 150, self.fonts["MEDIUM"], (200, 200, 200))

        if not games:
            draw_text(screen, "No games to display.", 50, 220, self.fonts["MEDIUM"], (200, 200, 200))
            return
            
        for i, game in enumerate(games):
            y_pos = 200 + i * 40
            draw_text(screen, str(game.get('name', 'N/A')), 50, y_pos, self.fonts["SMALL"], (255, 255, 255))
            draw_text(screen, str(game.get('current_version', 'N/A')), 350, y_pos, self.fonts["SMALL"], (255, 255, 255))
            # Truncate long descriptions
            desc = str(game.get('description', 'N/A'))
            if len(desc) > 30:
                desc = desc[:27] + "..."
            draw_text(screen, desc, 500, y_pos, self.fonts["SMALL"], (255, 255, 255))

    def draw_store_menu(self, screen):
        self._draw_game_table(screen, self.all_games, "Game Store")
        
    def draw_my_games_menu(self, screen):
        self._draw_game_table(screen, self.my_games, "My Games")

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
    client = PlayerGUI()
    client.run()
