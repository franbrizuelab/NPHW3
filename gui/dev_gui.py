# gui/dev_gui.py

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.base_gui import BaseGUI, draw_text

class DeveloperGUI(BaseGUI):
    def __init__(self):
        super().__init__(title="Developer Client")
        self.is_developer = False

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
                    self.client_state = "MAIN_MENU"
                    self.error_message = None
                else:
                    self.client_state = "ERROR"
                    self.error_message = "User is not a developer"
        else:
            # Fallback to base handling for other messages (like errors)
            super().handle_network_message(msg)

    def _attempt_registration(self):
        """Overrides base method to register a user as a developer."""
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            # Assumes the server can handle an 'is_developer' flag
            from client.shared import send_to_lobby_queue
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


if __name__ == "__main__":
    client = DeveloperGUI()
    client.run()
