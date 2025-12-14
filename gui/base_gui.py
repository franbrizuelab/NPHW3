# gui/base_gui.py

import pygame
import socket
import threading
import json
import sys
import os
import time
import logging
import queue
import select
import random

# Add project root to path BEFORE any other imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now import project modules
from common import config
from common import protocol
from common.game_rules import PIECE_SHAPES
from client.shared import g_lobby_send_queue, send_to_lobby_queue
from common.config import *

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# --- Base Configuration ---
# A slimmed-down version of the original CONFIG, focusing on shared UI elements.
# Specific screens can extend this.
BASE_CONFIG = {
    "TIMING": {"FPS": 30},
    "SCREEN": {"WIDTH": 900, "HEIGHT": 700},
    "SIZES": {"BLOCK_SIZE": 30, "SMALL_BLOCK_SIZE": 15},
    "STYLE": {"CORNER_RADIUS": 5},
    "COLORS": {
        "BACKGROUND": (20, 20, 30),
        "TEXT": (255, 255, 255),
        "BUTTON": (70, 70, 90),
        "BUTTON_HOVER": (100, 100, 120),
        "INPUT_BOX": (10, 10, 20),
        "INPUT_TEXT": (200, 200, 200),
        "INPUT_ACTIVE": (50, 50, 70),
        "ERROR": (200, 50, 50),
        "PIECE_COLORS": [
            (0, 0, 0),
            (1, 237, 250),  # Cyan
            (254, 251, 52),  # Yellow
            (128, 0, 128),  # Purple
            (0, 119, 211),    # BLue
            (255, 165, 0),  # Orange
            (57, 137, 47),     # Green
            (253, 63, 89)  # Salmon (reddish)
        ]
    },
    "FONTS": {
        "DEFAULT_FONT": 'assets/fonts/PressStart2P-Regular.ttf',
        "SIZES": {
            "TINY": 10,
            "SMALL": 15,
            "MEDIUM": 20,
            "LARGE": 25,
            "TITLE": 36,
        },
        "OBJECTS": {
            "DEFAULT": None,
            "TINY": None,
            "SMALL": None,
            "MEDIUM": None,
            "LARGE": None,
            "TITLE": None,
        }
    },
    "NETWORK": {
        "HOST": config.LOBBY_HOST,
        "PORT": config.LOBBY_PORT
    },
     "BACKGROUND_ANIMATION": {
        "NUM_PIECES": 20,
        "MIN_SIZE": 10,
        "MAX_SIZE": 50,
        "MIN_SPEED": 0.5,
        "MAX_SPEED": 4.0,
        "ALPHA": 50 # 0-255
    }
}


# --- UI Helper Classes ---

class TextInput:
    def __init__(self, x, y, w, h, font, text='', password=False, multiline=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = BASE_CONFIG["COLORS"]["INPUT_BOX"]
        self.text = text
        self.font = font
        self.active = False
        self.password = password
        self.multiline = multiline
        self.text_surfaces = [] # Store multiple surfaces for multiline
        self._update_surface()

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self.color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"] if self.active else BASE_CONFIG["COLORS"]["INPUT_BOX"]
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                if self.multiline:
                    self.text += '\n'
                else:
                    return "enter" # Only return "enter" for single-line inputs
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                self.text += event.unicode
            self._update_surface()

    def _update_surface(self):
        """Renders the text surfaces, masking and wrapping if necessary."""
        self.text_surfaces = []
        if self.multiline:
            lines = self.text.split('\n')
        else:
            lines = [self.text] # Treat as a single line
        
        for line in lines:
            display_text = line
            if self.password:
                display_text = '*' * len(line)
            self.text_surfaces.append(self.font.render(display_text, True, BASE_CONFIG["COLORS"]["INPUT_TEXT"]))

    def draw(self, screen):
        pygame.draw.rect(screen, self.color, self.rect, 0, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"])
        pygame.draw.rect(screen, BASE_CONFIG["COLORS"]["TEXT"], self.rect, 1, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"]) # Thin border
        
        y_offset = 0
        for text_surface in self.text_surfaces:
            screen.blit(text_surface, (self.rect.x + 5, self.rect.y + 5 + y_offset))
            y_offset += self.font.get_height()

class Button:
    def __init__(self, x, y, w, h, font, text=''):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = BASE_CONFIG["COLORS"]["BUTTON"]
        self.text = text
        self.font = font
        self.is_focused = False
    
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                return True
        return False
        
    def draw(self, screen, blink_on=True):
        color = self.color
        if self.rect.collidepoint(pygame.mouse.get_pos()) or self.is_focused:
            color = BASE_CONFIG["COLORS"]["BUTTON_HOVER"]
        pygame.draw.rect(screen, color, self.rect, 0, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"])
        
        if not self.is_focused or (self.is_focused and blink_on):
            text_surf = self.font.render(self.text, True, BASE_CONFIG["COLORS"]["TEXT"])
            text_rect = text_surf.get_rect(center=self.rect.center)
            screen.blit(text_surf, text_rect)

# --- Drawing Functions ---

def draw_text(surface, text, x, y, font, color):
    """Draws text using a pre-rendered font object."""
    try:
        text_surface = font.render(text, True, color)
        surface.blit(text_surface, (x, y))
    except Exception as e:
        print(f"Error rendering text: {e}")
        pass

# --- Background Animation ---
class FallingPiece:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.config = BASE_CONFIG["BACKGROUND_ANIMATION"]
        self.block_size = random.randint(self.config["MIN_SIZE"], self.config["MAX_SIZE"])
        self.color = random.choice(BASE_CONFIG["COLORS"]["PIECE_COLORS"][1:])
        self.speed = random.uniform(self.config["MIN_SPEED"], self.config["MAX_SPEED"])
        self.shape_id = random.randint(0, len(PIECE_SHAPES) - 1)
        self.rotation = random.randint(0, 3)
        self.x = random.randint(0, self.screen_width)
        self.y = random.uniform(-200, -50)

    def _get_blocks(self):
        """Get the (row, col) coordinates for the piece's current state."""
        shapes = PIECE_SHAPES[self.shape_id]
        shape = shapes[self.rotation % len(shapes)]
        return [(self.y + r * self.block_size, self.x + c * self.block_size) for r, c in shape]

    def update(self):
        self.y += self.speed
        if self.y > self.screen_height + 100:
            self.reset()

    def reset(self):
        self.y = random.uniform(-200, -50)
        self.x = random.randint(0, self.screen_width)
        self.block_size = random.randint(self.config["MIN_SIZE"], self.config["MAX_SIZE"])
        self.speed = random.uniform(self.config["MIN_SPEED"], self.config["MAX_SPEED"])
        self.color = random.choice(BASE_CONFIG["COLORS"]["PIECE_COLORS"][1:])
        self.shape_id = random.randint(0, len(PIECE_SHAPES) - 1)

    def draw(self, surface):
        blocks = self._get_blocks()
        for r, c in blocks:
            rect = pygame.Rect(c, r, self.block_size, self.block_size)
            block_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            fill_color = self.color + (self.config["ALPHA"],)
            pygame.draw.rect(block_surf, fill_color, block_surf.get_rect())
            border_color = self.color + (self.config["ALPHA"] + 50,)
            pygame.draw.rect(block_surf, border_color, block_surf.get_rect(), 1)
            surface.blit(block_surf, rect.topleft)

g_background_pieces = []

def draw_background(surface):
    surface.fill(BASE_CONFIG["COLORS"]["BACKGROUND"])
    
    global g_background_pieces
    if not g_background_pieces:
        num_pieces = BASE_CONFIG["BACKGROUND_ANIMATION"]["NUM_PIECES"]
        for _ in range(num_pieces):
            g_background_pieces.append(FallingPiece(BASE_CONFIG["SCREEN"]["WIDTH"], BASE_CONFIG["SCREEN"]["HEIGHT"]))

    for piece in g_background_pieces:
        piece.update()
        piece.draw(surface)


class BaseGUI:
    def __init__(self, title="Networked Application"):
        self.title = title
        self.state_lock = threading.Lock()
        self.client_state = "CONNECTING"
        self.running = True
        self.username = None
        self.error_message = None
        self.success_message = None
        self.lobby_socket = None
        self.ui_elements = {}
        self.fonts = {}
        self.screen = None
        self.clock = None
        self.focused_element_idx = 0

    def run(self):
        """Main entry point to start the GUI application."""
        self._init_pygame()
        self._load_fonts()
        self._create_ui_elements()
        self._start_network_thread()
        self._main_loop()
        self._cleanup()

    def _init_pygame(self):
        """Initializes Pygame and the main display screen."""
        os.environ['SDL_VIDEO_WINDOW_POS'] = "100,100"
        pygame.init()
        pygame.font.init()
        screen_size = (BASE_CONFIG["SCREEN"]["WIDTH"], BASE_CONFIG["SCREEN"]["HEIGHT"])
        self.screen = pygame.display.set_mode(size=screen_size)
        pygame.display.set_caption(self.title)
        self.clock = pygame.time.Clock()

    def _load_fonts(self):
        """Loads all necessary fonts."""
        font_path = BASE_CONFIG["FONTS"]["DEFAULT_FONT"]
        sizes = BASE_CONFIG["FONTS"]["SIZES"]
        try:
            for name, size in sizes.items():
                self.fonts[name.upper()] = pygame.font.Font(font_path, size)
        except pygame.error as e:
            logging.error(f"Error loading font: {e}. Falling back to default.")
            for name, size in sizes.items():
                self.fonts[name.upper()] = pygame.font.Font(None, size)
        self.fonts["DEFAULT"] = self.fonts["SMALL"]

    def _create_ui_elements(self):
        """Creates the initial UI elements for the login screen."""
        form_center_x = BASE_CONFIG["SCREEN"]["WIDTH"] // 2
        input_width = 300
        self.ui_elements = {
            "user_input": TextInput(form_center_x - input_width // 2, 220, input_width, 32, self.fonts["SMALL"]),
            "pass_input": TextInput(form_center_x - input_width // 2, 280, input_width, 32, self.fonts["SMALL"], password=True),
            "login_btn": Button(form_center_x - 150, 340, 140, 40, self.fonts["SMALL"], "Login"),
            "reg_btn": Button(form_center_x + 10, 340, 140, 40, self.fonts["SMALL"], "Register"),
            "login_focusable_elements": ["user_input", "pass_input", "login_btn", "reg_btn"],
            "back_btn": Button(BASE_CONFIG["SCREEN"]["WIDTH"] - 110, 10, 100, 40, self.fonts["SMALL"], "Back")
        }
        # Set initial focus to the first element (username input)
        self.ui_elements["user_input"].active = True
        self.ui_elements["user_input"].color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"]

    def _start_network_thread(self):
        """Starts the lobby network communication thread."""
        host = BASE_CONFIG["NETWORK"]["HOST"]
        port = BASE_CONFIG["NETWORK"]["PORT"]
        threading.Thread(
            target=self._lobby_network_thread,
            args=(host, port),
            daemon=True
        ).start()

    def _main_loop(self):
        """The main rendering and event-handling loop."""
        blink_on = True
        last_blink_time = 0

        while self.running:
            with self.state_lock:
                current_state = self.client_state

            # --- Event Handling ---
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                
                # Handle back button event globally if not on login screen
                if current_state not in ["LOGIN", "CONNECTING"]:
                    if self.ui_elements["back_btn"].handle_event(event):
                        self.handle_back_button(current_state)
                        continue # Skip other event handling for this event

                # Delegate event handling based on state
                if current_state == "LOGIN":
                    self._handle_login_events(event)
                else:
                    self.handle_custom_events(event, current_state)

            # --- Drawing ---
            draw_background(self.screen)

            if current_state == "CONNECTING":
                draw_text(self.screen, "Connecting...", 300, 300, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["TEXT"])
            elif current_state == "LOGIN":
                # Handle blinking for focused buttons
                current_time = time.time()
                if current_time - last_blink_time > 0.5:
                    blink_on = not blink_on
                    last_blink_time = current_time
                self._draw_login_screen(blink_on)
            else:
                # Draw the back button on all other screens
                self.ui_elements["back_btn"].draw(self.screen)
                if current_state == "MAIN_MENU":
                    self.draw_main_menu()
                elif current_state == "ERROR":
                    self._draw_error_screen()
                else:
                    self.draw_custom_state(self.screen, current_state)


            pygame.display.flip()
            self.clock.tick(BASE_CONFIG["TIMING"]["FPS"])

    def _draw_error_screen(self):
        """Draws a generic error screen."""
        draw_text(self.screen, "Error", 300, 100, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["ERROR"])
        if self.error_message:
            draw_text(self.screen, self.error_message, 100, 200, self.fonts["LARGE"], BASE_CONFIG["COLORS"]["ERROR"])

    def _handle_login_events(self, event):
        """Handles events specifically for the LOGIN screen."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                # Deactivate current focused element
                current_focused_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                if isinstance(self.ui_elements[current_focused_name], TextInput):
                    self.ui_elements[current_focused_name].active = False
                    self.ui_elements[current_focused_name].color = BASE_CONFIG["COLORS"]["INPUT_BOX"]
                elif isinstance(self.ui_elements[current_focused_name], Button):
                    self.ui_elements[current_focused_name].is_focused = False
                
                # Move to next element
                self.focused_element_idx = (self.focused_element_idx + 1) % len(self.ui_elements["login_focusable_elements"])
                
                # Activate new focused element
                new_focused_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                if isinstance(self.ui_elements[new_focused_name], TextInput):
                    self.ui_elements[new_focused_name].active = True
                    self.ui_elements[new_focused_name].color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"]
                elif isinstance(self.ui_elements[new_focused_name], Button):
                    self.ui_elements[new_focused_name].is_focused = True

            elif event.key == pygame.K_RETURN:
                current_focused_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                if current_focused_name == "login_btn":
                    self._attempt_login()
                elif current_focused_name == "reg_btn":
                    self._attempt_registration()
                elif current_focused_name in ["user_input", "pass_input"]:
                    self._attempt_login()
            else:
                # Pass other key events to the active text input
                self.ui_elements["user_input"].handle_event(event)
                self.ui_elements["pass_input"].handle_event(event)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Handle mouse clicks for all elements
            if self.ui_elements["login_btn"].handle_event(event):
                self._attempt_login()
            if self.ui_elements["reg_btn"].handle_event(event):
                self._attempt_registration()
            
            # This will set the active state on the text inputs
            self.ui_elements["user_input"].handle_event(event)
            self.ui_elements["pass_input"].handle_event(event)

    def _attempt_login(self):
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            self.username = user
            send_to_lobby_queue({
                "action": "login",
                "data": {"user": user, "pass": password}
            })
            with self.state_lock:
                self.error_message = None
    
    def _attempt_registration(self):
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            send_to_lobby_queue({
                "action": "register",
                "data": {"user": user, "pass": password}
            })
            with self.state_lock:
                self.error_message = None


    def _draw_login_screen(self, blink_on=True):
        """Draws the login form."""
        draw_text(self.screen, "Welcome", 350, 100, self.fonts["LARGE"], BASE_CONFIG["COLORS"]["TEXT"])
        
        form_center_x = BASE_CONFIG["SCREEN"]["WIDTH"] // 2
        
        draw_text(self.screen, "Username:", form_center_x - 150, 200, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["TEXT"])
        self.ui_elements["user_input"].draw(self.screen)
        draw_text(self.screen, "Password:", form_center_x - 150, 260, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["TEXT"])
        self.ui_elements["pass_input"].draw(self.screen)
        
        self.ui_elements["login_btn"].draw(self.screen, blink_on)
        self.ui_elements["reg_btn"].draw(self.screen, blink_on)
        
        with self.state_lock:
            error_msg = self.error_message
        if error_msg:
            error_x = form_center_x - self.fonts["MEDIUM"].size(error_msg)[0] // 2
            draw_text(self.screen, error_msg, error_x, 400, self.fonts["MEDIUM"], BASE_CONFIG["COLORS"]["ERROR"])

    def draw_main_menu(self):
        """A placeholder for the main menu screen."""
        draw_text(self.screen, "Main Menu", 350, 300, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["TEXT"])


    def _lobby_network_thread(self, host, port):
        """Handles network communication with the lobby server."""
        try:
            logging.info(f"Connecting to lobby server at {host}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            self.lobby_socket = sock
            logging.info("Connected!")
            with self.state_lock:
                self.client_state = "LOGIN"
        except socket.error as e:
            logging.critical(f"Failed to connect to lobby: {e}")
            with self.state_lock:
                self.error_message = f"Failed to connect: {e}"
                self.client_state = "ERROR"
            self.running = False
            return

        while self.running:
            readable, _, exceptional = select.select([sock], [], [sock], 0.1)

            if exceptional:
                logging.error("Lobby socket exception.")
                self.running = False
                break
            
            # --- RECEIVE ---
            if sock in readable:
                data_bytes = protocol.recv_msg(sock)
                if data_bytes is None:
                    if self.running:
                        logging.warning("Lobby server disconnected.")
                        self.running = False
                    break
                
                msg = json.loads(data_bytes.decode('utf-8'))
                self.handle_network_message(msg)

            # --- SEND ---
            try:
                while not g_lobby_send_queue.empty():
                    request = g_lobby_send_queue.get_nowait()
                    json_bytes = json.dumps(request).encode('utf-8')
                    protocol.send_msg(sock, json_bytes)
            except queue.Empty:
                pass
        
        logging.info("Lobby network thread exiting.")

    def handle_network_message(self, msg):
        """Processes messages from the lobby server. To be overridden."""
        logging.info(f"Received: {msg}")
        status = msg.get("status")
        reason = msg.get("reason")

        if status == "ok" and reason == "login_successful":
            with self.state_lock:
                self.client_state = "MAIN_MENU"
                self.error_message = None
        elif status == "error":
            with self.state_lock:
                self.error_message = reason

    def _cleanup(self):
        """Cleans up resources before exiting."""
        logging.info("Shutting down...")
        if self.lobby_socket:
            self.lobby_socket.close()
        pygame.quit()

    def handle_back_button(self, current_state):
        """Default back button behavior: return to login screen and log out."""
        if self.username: # Only send logout if logged in
            from client.shared import send_to_lobby_queue
            send_to_lobby_queue({"action": "logout"})
            
        with self.state_lock:
            self.client_state = "LOGIN"
            self.username = None # Clear username on logout
            self.error_message = None # Clear any error messages

    # --- Methods to be overridden by subclasses ---

    def draw_custom_state(self, screen, state):
        """Placeholder for drawing subclass-specific states."""
        pass

    def handle_custom_events(self, event, state):
        """Placeholder for handling subclass-specific events."""
        pass

