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

logging.basicConfig(level=logging.INFO, format='[BASE_GUI] %(asctime)s - %(levelname)s: %(message)s')

# --- Base Configuration ---
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
            (0, 0, 0), (1, 237, 250), (254, 251, 52), (128, 0, 128),
            (0, 119, 211), (255, 165, 0), (57, 137, 47), (253, 63, 89)
        ]
    },
    "FONTS": {
        "DEFAULT_FONT": 'assets/fonts/PressStart2P-Regular.ttf',
        "SIZES": {
            "TINY": 10, "SMALL": 15, "MEDIUM": 20, "LARGE": 25, "TITLE": 36,
        },
        "OBJECTS": {}
    },
    "NETWORK": {
        "HOST": config.LOBBY_HOST,
        "PORT": config.LOBBY_PORT
    },
    "BACKGROUND_ANIMATION": {
        "NUM_PIECES": 20, "MIN_SIZE": 10, "MAX_SIZE": 50,
        "MIN_SPEED": 0.5, "MAX_SPEED": 4.0, "ALPHA": 50
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
        self.text_surfaces = []
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
                    return "enter"
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                self.text += event.unicode
            self._update_surface()

    def _update_surface(self):
        self.text_surfaces = []
        lines = self.text.split('\n')
        for line in lines:
            display_text = '*' * len(line) if self.password else line
            self.text_surfaces.append(self.font.render(display_text, True, BASE_CONFIG["COLORS"]["INPUT_TEXT"]))

    def draw(self, screen):
        pygame.draw.rect(screen, self.color, self.rect, 0, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"])
        pygame.draw.rect(screen, BASE_CONFIG["COLORS"]["TEXT"], self.rect, 1, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"])
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
            return self.rect.collidepoint(event.pos)
        return False
        
    def draw(self, screen, blink_on=True):
        color = self.color
        if self.rect.collidepoint(pygame.mouse.get_pos()) or self.is_focused:
            color = BASE_CONFIG["COLORS"]["BUTTON_HOVER"]
        pygame.draw.rect(screen, color, self.rect, 0, border_radius=BASE_CONFIG["STYLE"]["CORNER_RADIUS"])
        if not self.is_focused or blink_on:
            text_surf = self.font.render(self.text, True, BASE_CONFIG["COLORS"]["TEXT"])
            text_rect = text_surf.get_rect(center=self.rect.center)
            screen.blit(text_surf, text_rect)

# --- Drawing Functions ---

def draw_text(surface, text, x, y, font, color):
    try:
        text_surface = font.render(text, True, color)
        surface.blit(text_surface, (x, y))
    except Exception as e:
        print(f"Error rendering text: {e}")

# --- Background Animation ---
g_background_pieces = []
def draw_background(surface):
    surface.fill(BASE_CONFIG["COLORS"]["BACKGROUND"])
    global g_background_pieces
    if not g_background_pieces:
        for _ in range(BASE_CONFIG["BACKGROUND_ANIMATION"]["NUM_PIECES"]):
            g_background_pieces.append(FallingPiece(BASE_CONFIG["SCREEN"]["WIDTH"], BASE_CONFIG["SCREEN"]["HEIGHT"]))
    for piece in g_background_pieces:
        piece.update()
        piece.draw(surface)

class FallingPiece:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.config = BASE_CONFIG["BACKGROUND_ANIMATION"]
        self.reset()
        self.y = random.uniform(-200, self.h)
    def reset(self):
        self.block_size = random.randint(self.config["MIN_SIZE"], self.config["MAX_SIZE"])
        self.color = random.choice(BASE_CONFIG["COLORS"]["PIECE_COLORS"][1:])
        self.speed = random.uniform(self.config["MIN_SPEED"], self.config["MAX_SPEED"])
        self.shape_id = random.randint(0, len(PIECE_SHAPES) - 1)
        self.rotation = random.randint(0, 3)
        self.x = random.randint(0, self.w)
        self.y = random.uniform(-200, -50)
    def update(self):
        self.y += self.speed
        if self.y > self.h + 100: self.reset()
    def draw(self, surface):
        shape = PIECE_SHAPES[self.shape_id][self.rotation % len(PIECE_SHAPES[self.shape_id])]
        for r, c in shape:
            rect = pygame.Rect(self.x + c * self.block_size, self.y + r * self.block_size, self.block_size, self.block_size)
            block_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            block_surf.fill(self.color + (self.config["ALPHA"],))
            pygame.draw.rect(block_surf, self.color + (self.config["ALPHA"] + 50,), block_surf.get_rect(), 1)
            surface.blit(block_surf, rect.topleft)

# --- Main GUI Class ---

class BaseGUI:
    def __init__(self, title="Networked Application"):
        self.title = title
        self.state_lock = threading.Lock()
        self.client_state = "CONNECTING"
        self.running = True
        self.username = None
        self.error_message = None
        self.lobby_socket = None
        self.ui_elements = {}
        self.fonts = {}
        self.screen = None
        self.clock = None
        self.focused_element_idx = 0
        self.network_thread = None

    def run(self):
        self._init_pygame()
        self._load_fonts()
        self._create_ui_elements()
        self._start_network_thread()
        self._main_loop()
        self._cleanup()

    def _init_pygame(self):
        os.environ['SDL_VIDEO_WINDOW_POS'] = "100,100"
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((BASE_CONFIG["SCREEN"]["WIDTH"], BASE_CONFIG["SCREEN"]["HEIGHT"]))
        pygame.display.set_caption(self.title)
        self.clock = pygame.time.Clock()

    def _load_fonts(self):
        font_path = BASE_CONFIG["FONTS"]["DEFAULT_FONT"]
        sizes = BASE_CONFIG["FONTS"]["SIZES"]
        try:
            for name, size in sizes.items():
                self.fonts[name.upper()] = pygame.font.Font(font_path, size)
        except pygame.error:
            for name, size in sizes.items():
                self.fonts[name.upper()] = pygame.font.Font(None, size)
        self.fonts["DEFAULT"] = self.fonts["SMALL"]

    def _create_ui_elements(self):
        center_x, w = BASE_CONFIG["SCREEN"]["WIDTH"] // 2, 300
        self.ui_elements = {
            "user_input": TextInput(center_x - w // 2, 220, w, 32, self.fonts["SMALL"]),
            "pass_input": TextInput(center_x - w // 2, 280, w, 32, self.fonts["SMALL"], password=True),
            "login_btn": Button(center_x - 150, 340, 140, 40, self.fonts["SMALL"], "Login"),
            "reg_btn": Button(center_x + 10, 340, 140, 40, self.fonts["SMALL"], "Register"),
            "back_btn": Button(BASE_CONFIG["SCREEN"]["WIDTH"] - 110, 10, 100, 40, self.fonts["SMALL"], "Back"),
            "login_focusable_elements": ["user_input", "pass_input", "login_btn", "reg_btn"]
        }
        self.ui_elements["user_input"].active = True
        self.ui_elements["user_input"].color = BASE_CONFIG["COLORS"]["INPUT_ACTIVE"]

    def _main_loop(self):
        blink_on = True
        last_blink_time = 0
        while self.running:
            with self.state_lock: current_state = self.client_state
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
                # Handle back button event globally if logged in and not on a connection screen
                # Don't allow back button on main menu screens (first screen after login)
                # MY_GAMES_MENU back button handling is done by child classes for player client
                if (self.username and current_state not in ["LOGIN", "CONNECTING", "LOGGING_OUT", "LOBBY_MENU"] 
                    and self.ui_elements["back_btn"].handle_event(event)):
                    # Allow child classes to handle MY_GAMES_MENU back button
                    if current_state == "MY_GAMES_MENU":
                        # Let child class handle it in handle_custom_events
                        pass  # Event will continue to handle_custom_events
                    else:
                        self.handle_back_button(current_state)
                        continue  # Skip further processing
                if current_state == "LOGIN": self._handle_login_events(event)
                else: self.handle_custom_events(event, current_state)
            
            draw_background(self.screen)
            if current_state == "CONNECTING":
                draw_text(self.screen, "Connecting...", 300, 300, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["TEXT"])
            elif current_state == "LOGIN":
                if time.time() - last_blink_time > 0.5:
                    blink_on = not blink_on
                    last_blink_time = time.time()
                self._draw_login_screen(blink_on)
            elif current_state == "LOGGING_OUT":
                draw_text(self.screen, "Logging out...", 300, 300, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["TEXT"])
            elif current_state == "ERROR":
                self._draw_error_screen()
            else:
                # Don't draw back button on main menu screens (first screen after login)
                # Player: LOBBY_MENU (MY_GAMES_MENU can have back button), Developer: MY_GAMES_MENU
                if current_state not in ["LOBBY_MENU"]:
                    # Check if we're in MY_GAMES_MENU - only allow back button for player client
                    # This will be handled by child classes if needed
                    if current_state == "MY_GAMES_MENU":
                        # Child classes can override draw_custom_state to show back button if needed
                        pass
                    else:
                        self.ui_elements["back_btn"].draw(self.screen)
                self.draw_custom_state(self.screen, current_state)
            
            pygame.display.flip()
            self.clock.tick(BASE_CONFIG["TIMING"]["FPS"])

    def _handle_login_events(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                # Simple focus cycling
                current_focus_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                self.ui_elements[current_focus_name].active = False
                self.ui_elements[current_focus_name].is_focused = False
                self.focused_element_idx = (self.focused_element_idx + 1) % len(self.ui_elements["login_focusable_elements"])
                new_focus_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                self.ui_elements[new_focus_name].active = True
                self.ui_elements[new_focus_name].is_focused = True
            elif event.key == pygame.K_RETURN:
                focused_name = self.ui_elements["login_focusable_elements"][self.focused_element_idx]
                if focused_name == "login_btn": self._attempt_login()
                elif focused_name == "reg_btn": self._attempt_registration()
                else: self._attempt_login()
            else:
                for name in ["user_input", "pass_input"]: self.ui_elements[name].handle_event(event)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.ui_elements["login_btn"].handle_event(event): self._attempt_login()
            if self.ui_elements["reg_btn"].handle_event(event): self._attempt_registration()
            for name in ["user_input", "pass_input"]: self.ui_elements[name].handle_event(event)

    def _draw_login_screen(self, blink_on=True):
        draw_text(self.screen, "Welcome", 350, 100, self.fonts["LARGE"], BASE_CONFIG["COLORS"]["TEXT"])
        draw_text(self.screen, "Username:", 290, 200, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["TEXT"])
        self.ui_elements["user_input"].draw(self.screen)
        draw_text(self.screen, "Password:", 290, 260, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["TEXT"])
        self.ui_elements["pass_input"].draw(self.screen)
        self.ui_elements["login_btn"].draw(self.screen, blink_on)
        self.ui_elements["reg_btn"].draw(self.screen, blink_on)
        if self.error_message:
            # Use SMALL font for error messages and truncate if too long
            error_text = self.error_message
            if len(error_text) > 60:
                error_text = error_text[:57] + "..."
            err_size = self.fonts["SMALL"].size(error_text)
            draw_text(self.screen, error_text, (BASE_CONFIG["SCREEN"]["WIDTH"] - err_size[0]) // 2, 400, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["ERROR"])

    def _draw_error_screen(self):
        draw_text(self.screen, "Error", 350, 100, self.fonts["TITLE"], BASE_CONFIG["COLORS"]["ERROR"])
        if self.error_message:
            # Use SMALL font and wrap/truncate long messages
            error_text = self.error_message
            if len(error_text) > 60:
                error_text = error_text[:57] + "..."
            draw_text(self.screen, error_text, 150, 200, self.fonts["SMALL"], BASE_CONFIG["COLORS"]["ERROR"])

    def _attempt_login(self):
        user, password = self.ui_elements["user_input"].text, self.ui_elements["pass_input"].text
        if user and password:
            self.username = user
            send_to_lobby_queue({"action": "login", "data": {"user": user, "pass": password}})
            with self.state_lock: self.error_message = None
    
    def _attempt_registration(self):
        """Queues the registration request and creates user download directory."""
        user = self.ui_elements["user_input"].text
        password = self.ui_elements["pass_input"].text
        if user and password:
            # Create the user's download directory ahead of time
            try:
                user_download_dir = os.path.join("player", "downloads", user)
                os.makedirs(user_download_dir, exist_ok=True)
                logging.info(f"Ensured download directory exists: {user_download_dir}")
            except OSError as e:
                logging.error(f"Failed to create download directory: {e}")
                # Decide if we should stop registration or just log the error
                # For now, we'll log and continue.

            send_to_lobby_queue({
                "action": "register",
                "data": {"user": user, "pass": password}
            })
            with self.state_lock:
                self.error_message = None

    def _start_network_thread(self):
        self.network_thread = threading.Thread(target=self._lobby_network_thread, daemon=True)
        self.network_thread.start()

    def _lobby_network_thread(self):
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
                    if self.client_state == "LOGGING_OUT": self.client_state = "LOGIN"; self.username = None
                    else: self.client_state = "ERROR"; self.error_message = "Connection lost"

    def handle_network_message(self, msg):
        logging.info(f"[RECV] {msg}")
        status, reason = msg.get("status"), msg.get("reason")
        with self.state_lock:
            if status == "ok" and reason == "login_successful":
                self.client_state = "MAIN_MENU"; self.error_message = None
            elif status == "ok" and reason == "logout_successful": pass
            elif status == "error":
                self.error_message = reason
                # Don't force logout on errors - let subclasses handle it
                # Only reset to LOGIN if it's a critical authentication error
                if reason in ["must_be_logged_in", "session_expired", "invalid_credentials"]:
                    if self.client_state not in ["LOGIN", "CONNECTING"]:
                        self.client_state = "LOGIN"
                        self.username = None

    def handle_back_button(self, current_state):
        """Initiates logout by sending a message and then closing the socket."""
        if self.username:
            logging.info(f"Queuing logout for user: {self.username}")
            send_to_lobby_queue({"action": "logout"})
            # Give network thread a moment to send the message before we close the socket
            time.sleep(0.1)
            if self.lobby_socket:
                self.lobby_socket.close()
                self.lobby_socket = None # Ensure it's None so the net thread tries to reconnect
                # The network thread will detect the closed socket and reset state
        
        # In all cases, transition UI state
        with self.state_lock:
            self.client_state = "LOGIN"
            self.username = None
            self.error_message = None

    def _cleanup(self):
        """Cleans up resources before exiting."""
        logging.info("Shutting down...")
        self.running = False
        if self.lobby_socket and self.username:
            try:
                logging.info("Sending final logout on exit...")
                send_to_lobby_queue({"action": "logout"})
                time.sleep(0.1) # Brief moment to allow queue to be processed
            except Exception as e:
                logging.error(f"Error sending final logout: {e}")
            finally:
                self.lobby_socket.close()
        
        if self.network_thread and self.network_thread.is_alive():
            self.network_thread.join(timeout=0.5)
            
        pygame.quit()

    def draw_custom_state(self, screen, state): pass
    def handle_custom_events(self, event, state): pass