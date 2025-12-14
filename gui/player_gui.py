# gui/player_gui.py

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui.base_gui import BaseGUI, draw_text

class PlayerGUI(BaseGUI):
    def __init__(self):
        super().__init__(title="Player Client")

    # Override methods for player-specific functionality
    def draw_custom_state(self, screen, state):
        # In the future, this will handle LOBBY, IN_ROOM, GAME states
        draw_text(screen, f"Player State: {state}", 100, 100, self.fonts["MEDIUM"], (255, 255, 255))

    def handle_custom_events(self, event, state):
        # Handle events for LOBBY, IN_ROOM, GAME
        pass

    def handle_network_message(self, msg):
        # Handle network messages for game updates, invites, etc.
        super().handle_network_message(msg)


if __name__ == "__main__":
    client = PlayerGUI()
    client.run()
