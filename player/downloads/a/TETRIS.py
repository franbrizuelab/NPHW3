#!/usr/bin/env python3
"""
Tetris Game Server
A self-contained game file that includes:
- Game logic (TetrisGame, Piece classes)
- Game server (network handling, game loop)
- Can be launched by the lobby server

This file should be placed in developer/games/ and uploaded to the system.
"""

import socket
import threading
import json
import sys
import os
import time
import random
import queue
import logging
import argparse
import select
from datetime import datetime

# Add project root to path to access common modules
# This works whether the file is in developer/games/, storage/games/, or player/downloads/{username}/
current_dir = os.path.dirname(os.path.abspath(__file__))

# Search upward from current directory to find project root (directory containing "common")
project_root = None
search_dir = current_dir
max_levels = 10  # Go up at most 10 levels
for _ in range(max_levels):
    common_path = os.path.join(search_dir, "common")
    if os.path.exists(common_path) and os.path.isdir(common_path):
        project_root = search_dir
        break
    parent = os.path.dirname(search_dir)
    if parent == search_dir:  # Reached filesystem root
        break
    search_dir = parent

if project_root:
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # logging not imported yet, use print for debugging
    # logging.debug(f"Found project root: {project_root}")
else:
    print(f"ERROR: Could not find project root. Searched from: {current_dir}")

try:
    from common import config
    from common import protocol
except ImportError as e:
    print(f"Error: Could not import common modules (protocol, config).")
    print(f"Import error: {e}")
    print(f"Current directory: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"Project root: {project_root}")
    print(f"Python path: {sys.path[:3]}")
    print("Ensure this file is in the correct location relative to the 'common' folder.")
    sys.exit(1)

# ============================================================================
# GAME LOGIC (TetrisGame and Piece classes)
# ============================================================================

# Constants
BOARD_WIDTH = 10
BOARD_HEIGHT = 20

# Standard Tetris piece shapes and their rotations
# 0: I, 1: O, 2: T, 3: J, 4: L, 5: S, 6: Z
# Each tuple represents (row, col) offsets from a pivot point
PIECE_SHAPES = (
    # I
    (((0, -2), (0, -1), (0, 0), (0, 1)),  # 0 deg
     ((-2, 0), (-1, 0), (0, 0), (1, 0))), # 90 deg
    # O
    (((0, 0), (0, 1), (1, 0), (1, 1)),),  
    # T
    (((0, -1), (0, 0), (0, 1), (1, 0)),   # 0 deg
     ((-1, 0), (0, 0), (1, 0), (0, -1)),  # 90 deg
     ((0, -1), (0, 0), (0, 1), (-1, 0)),  # 180 deg
     ((-1, 0), (0, 0), (1, 0), (0, 1))),   # 270 deg
    # J
    (((0, -1), (0, 0), (0, 1), (-1, 1)),  # 0 deg
     ((-1, 0), (0, 0), (1, 0), (1, 1)),   # 90 deg
     ((0, -1), (0, 0), (0, 1), (1, -1)),  # 180 deg
     ((-1, -1), (-1, 0), (0, 0), (1, 0))), # 270 deg
    # L
    (((0, -1), (0, 0), (0, 1), (-1, -1)), 
     ((-1, 0), (0, 0), (1, 0), (1, -1)),  
     ((0, -1), (0, 0), (0, 1), (1, 1)),   
     ((-1, 1), (-1, 0), (0, 0), (1, 0))),  
    # S
    (((0, -1), (0, 0), (1, 0), (1, 1)),   
     ((-1, 1), (0, 0), (0, 1), (1, 0))),   
    # Z
    (((0, 0), (0, 1), (1, -1), (1, 0)),   
     ((-1, 0), (0, 0), (0, 1), (1, 1)))  
)

# Scoring: {lines_cleared: points}
SCORING = {
    0: 0,
    1: 100,
    2: 300,
    3: 500,
    4: 800
}

class Piece:
    """Represents a single falling Tetris piece."""
    def __init__(self, shape_id: int):
        self.shape_id = shape_id
        self.shapes = PIECE_SHAPES[shape_id]
        self.rotation = 0
        
        # Spawn position
        self.x = BOARD_WIDTH // 2
        self.y = 0 if shape_id != 0 else 1  # 'I' piece spawns a bit higher

    def get_blocks(self):
        """Get the (row, col) coordinates for the piece's current state."""
        shape = self.shapes[self.rotation % len(self.shapes)]
        # Absolute (r,c) coordinates for each block 
        return [(self.y + r, self.x + c) for r, c in shape]

    def get_next_rotation(self):
        """Get the coordinates for the next rotation state."""
        next_rot = (self.rotation + 1) % len(self.shapes)
        shape = self.shapes[next_rot]
        return [(self.y + r, self.x + c) for r, c in shape]

class TetrisGame:
    """Manages the state of one Tetris board."""
    
    def __init__(self, seed: int):
        self.board = self._create_empty_board()
        self.score = 0
        self.lines_cleared = 0
        self.game_over = False
        
        # Use a seedable RNG for deterministic piece sequences
        self._rng = random.Random(seed)
        self._bag = []
        
        self.next_piece = self._get_from_bag()
        self.current_piece = None
        self._spawn_new_piece()

    def _create_empty_board(self):
        # 0 represents an empty cell
        return [[0 for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

    def _get_from_bag(self):
        """Implements the 7-bag piece randomizer."""
        if not self._bag:
            # Refill the bag when empty
            self._bag = list(range(len(PIECE_SHAPES)))
            self._rng.shuffle(self._bag)
        
        # Return a new Piece object
        return Piece(self._bag.pop())

    def _spawn_new_piece(self):
        """Promotes next_piece to current and checks for game over."""
        self.current_piece = self.next_piece
        self.next_piece = self._get_from_bag()
        
        # Check for game over (spawn collision)
        if self._check_collision(self.current_piece.get_blocks()):
            self.game_over = True
            # Set piece to None so it doesn't get drawn
            self.current_piece = None

    def _check_collision(self, blocks: list) -> bool:
        """Checks if a piece's blocks are in an invalid position."""
        for y, x in blocks:
            # Check wall bounds
            if x < 0 or x >= BOARD_WIDTH:
                return True
            # Check floor bounds (only bottom)
            if y >= BOARD_HEIGHT:
                return True
            # Check board (only for visible rows)
            if y >= 0 and self.board[y][x] != 0:
                return True
        return False

    def _lock_piece(self):
        """Stamps the current piece onto the board."""
        if self.current_piece is None:
            return
            
        blocks = self.current_piece.get_blocks()
        
        for y, x in blocks:
            # Only lock blocks that are on the visible board
            if 0 <= y < BOARD_HEIGHT and 0 <= x < BOARD_WIDTH:
                # Use shape_id + 1 as the color/block ID
                self.board[y][x] = self.current_piece.shape_id + 1
        
        self._clear_lines()
        self._spawn_new_piece()

    def _clear_lines(self):
        """Checks for and clears completed lines."""
        new_board = []
        lines_to_clear = []
        
        # Find full lines from bottom up
        for r_idx in range(BOARD_HEIGHT - 1, -1, -1):
            row = self.board[r_idx]
            if 0 not in row:
                lines_to_clear.append(r_idx)
            else:
                new_board.insert(0, row)
        
        lines_count = len(lines_to_clear)
        if lines_count > 0:
            # Add points
            self.score += SCORING.get(lines_count, 0)
            self.lines_cleared += lines_count
            # Add new empty rows at the top
            for _ in range(lines_count):
                new_board.insert(0, [0 for _ in range(BOARD_WIDTH)])
            
            self.board = new_board

    # Public API (called by Game Server)
    def move(self, direction: str):
        """Move the current piece 'left' or 'right'."""
        if self.game_over or self.current_piece is None:
            return

        dx = -1 if direction == 'left' else 1
        
        # Get blocks at new position
        new_blocks = [(y, x + dx) for y, x in self.current_piece.get_blocks()]
        
        if not self._check_collision(new_blocks):
            # Commit the move
            self.current_piece.x += dx

    def rotate(self):
        """Rotate the current piece clockwise."""
        if self.game_over or self.current_piece is None:
            return
            
        new_blocks = self.current_piece.get_next_rotation()
        
        # This is a simple rotation, no complex wall kicks
        if not self._check_collision(new_blocks):
            # Commit the rotation
            self.current_piece.rotation += 1

    def tick(self):
        """Called periodically to apply gravity (move piece down)."""
        self.soft_drop()

    def soft_drop(self):
        """Move the current piece down by one, or lock if it collides."""
        if self.game_over or self.current_piece is None:
            return
            
        # Get blocks at new position
        new_blocks = [(y + 1, x) for y, x in self.current_piece.get_blocks()]
        
        if self._check_collision(new_blocks):
            # Landed. Lock the piece.
            self._lock_piece()
        else:
            # Commit the move
            self.current_piece.y += 1
    
    def hard_drop(self):
        """Instantly drop and lock the piece."""
        if self.game_over or self.current_piece is None:
            return
        
        # Keep moving down until we collide
        while not self._check_collision([(y + 1, x) for y, x in self.current_piece.get_blocks()]):
            self.current_piece.y += 1
            
        # Once we'd collide on the next drop, lock it
        self._lock_piece()

    def get_state_snapshot(self) -> dict:
        """
        Returns the complete state of the game as a
        JSON-serializable dictionary for the server to broadcast.
        """
        
        # Get current piece info (if it exists)
        current_piece_data = None
        if self.current_piece:
            current_piece_data = {
                "shape_id": self.current_piece.shape_id,
                "blocks": self.current_piece.get_blocks()
            }
        
        # Get next piece info
        next_piece_data = {
            "shape_id": self.next_piece.shape_id,
            # We only need to show the shape, not its position
            "blocks": [(r, c + 3) for r, c in PIECE_SHAPES[self.next_piece.shape_id][0]]
        }
            
        return {
            "board": self.board,
            "score": self.score,
            "lines": self.lines_cleared,
            "game_over": self.game_over,
            "current_piece": current_piece_data,
            "next_piece": next_piece_data
        }

# ============================================================================
# GAME SERVER (Network handling and game loop)
# ============================================================================

# Configuration
GRAVITY_INTERVAL_MS = 400  # How often pieces fall (in ms)
GAME_DURATION_SECONDS = 60  # Game duration in seconds

# Configure logging
logging.basicConfig(level=logging.INFO, format='[TETRIS_GAME] %(asctime)s - %(message)s')

def handle_client(sock: socket.socket, player_id: int, input_queue: queue.Queue):
    """
    Runs in a thread for each client (P1 and P2).
    Listens for INPUT messages and puts them in the shared queue.
    """
    logging.info(f"Client thread started for Player {player_id + 1}.")
    try:
        while True:
            # Block waiting for a message
            data_bytes = protocol.recv_msg(sock)
            if data_bytes is None:
                logging.warning(f"Player {player_id + 1} disconnected.")
                input_queue.put((player_id, "DISCONNECT"))
                break
            
            try:
                request = json.loads(data_bytes.decode('utf-8'))
                if request.get("type") == "INPUT":
                    action = request.get("action")
                    if action:
                        # Put the input into the queue for the main loop
                        input_queue.put((player_id, action))
                elif request.get("type") == "FORFEIT":
                    input_queue.put((player_id, "FORFEIT"))
                
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logging.warning(f"Invalid JSON from Player {player_id + 1}: {e}")
            
    except socket.error as e:
        logging.error(f"Socket error for Player {player_id + 1}: {e}")
        input_queue.put((player_id, "DISCONNECT"))
    finally:
        sock.close()
        logging.info(f"Client thread stopped for Player {player_id + 1}.")

def broadcast_state(clients: list, game_p1: TetrisGame, game_p2: TetrisGame, remaining_time: int):
    """
    Builds the snapshot and sends it to both clients.
    """
    try:
        p1_state = game_p1.get_state_snapshot()
        p2_state = game_p2.get_state_snapshot()
        
        snapshot = {
            "type": "SNAPSHOT",
            "p1_state": p1_state,
            "p2_state": p2_state,
            "remaining_time": remaining_time
        }
        
        json_bytes = json.dumps(snapshot).encode('utf-8')
        
        # Send the *same* snapshot to both clients
        for sock in clients:
            if sock:
                protocol.send_msg(sock, json_bytes)
                
    except socket.error as e:
        logging.warning(f"Failed to broadcast state: {e}. One client may have disconnected.")
    except Exception as e:
        logging.error(f"Error in broadcast_state: {e}", exc_info=True)

def process_input(game: TetrisGame, action: str):
    """Maps an action string to a game logic function."""
    if action == "MOVE_LEFT":
        game.move("left")
    elif action == "MOVE_RIGHT":
        game.move("right")
    elif action == "ROTATE":
        game.rotate()
    elif action == "SOFT_DROP":
        game.soft_drop()
    elif action == "HARD_DROP":
        game.hard_drop()

def forward_to_db(request: dict) -> dict | None:
    """Acts as a client to the DB_Server."""
    try:
        # Use config for DB host/port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((config.DB_HOST, config.DB_PORT))
            request_bytes = json.dumps(request).encode('utf-8')
            protocol.send_msg(sock, request_bytes)
            response_bytes = protocol.recv_msg(sock)
            
            if response_bytes:
                return json.loads(response_bytes.decode('utf-8'))
            else:
                logging.warning("DB server closed connection unexpectedly.")
                return {"status": "error", "reason": "db_server_no_response"}
                
    except socket.error as e:
        logging.error(f"Failed to connect or communicate with DB server: {e}")
        return {"status": "error", "reason": f"db_server_connection_error: {e}"}

def handle_game_end(clients: list, game_p1: TetrisGame, game_p2: TetrisGame, winner: str, reason: str, 
                   loser_username: str, p1_user: str, p2_user: str, room_id: int, start_time: float):
    """
    Handles all end-of-game logic:
    1. Builds the GameLog.
    2. Reports the log to the DB server.
    3. Sends the final GAME_OVER message to both clients.
    4. Notifies the lobby server that the game is over.
    """
    logging.info(f"Game loop finished. Winner: {winner}, Reason: {reason}")
    end_time = datetime.now()
    
    # 1. Build GameLog
    p1_results = {"userId": p1_user, "score": game_p1.score, "lines": game_p1.lines_cleared}
    p2_results = {"userId": p2_user, "score": game_p2.score, "lines": game_p2.lines_cleared}
    
    game_log = {
        "matchid": f"match_{int(time.time())}",
        "users": [p1_user, p2_user],  # Use real usernames
        "results": [p1_results, p2_results],
        "winner": winner,
        "reason": reason,
        "start_time": datetime.fromtimestamp(start_time).isoformat(),
        "end_time": end_time.isoformat()
    }

    # 2. Report to DB
    db_response = forward_to_db({
        "collection": "GameLog",
        "action": "create",
        "data": game_log
    })
    if db_response and db_response.get("status") == "ok":
        logging.info("GameLog saved to DB.")
    else:
        logging.warning(f"Failed to save GameLog to DB: {db_response}")

    # 3. Send final GAME_OVER message to clients
    winner_username = "TIE"
    if winner == "P1":
        winner_username = p1_user
    elif winner == "P2":
        winner_username = p2_user
        
    game_over_msg = {
        "type": "GAME_OVER",
        "winner": winner,
        "reason": reason,
        "loser_username": loser_username,
        "winner_username": winner_username,
        "p1_results": p1_results,
        "p2_results": p2_results,
        "room_id": room_id
    }

    try:
        for sock in list(clients):
            if sock:
                protocol.send_msg(sock, json.dumps(game_over_msg).encode('utf-8'))
    except Exception as e:
        logging.warning(f"Failed to send GAME_OVER message: {e}")
    
    # 4. Notify the lobby server that the game is over
    try:
        lobby_request = {
            "action": "game_over",
            "data": {"room_id": room_id}
        }
        # Connect to lobby server to notify it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as lobby_sock:
            lobby_sock.settimeout(5.0)
            lobby_sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
            request_bytes = json.dumps(lobby_request).encode('utf-8')
            protocol.send_msg(lobby_sock, request_bytes)
            # Wait for response (optional, but good practice)
            response_bytes = protocol.recv_msg(lobby_sock)
            if response_bytes:
                response = json.loads(response_bytes.decode('utf-8'))
                if response.get("status") == "ok":
                    logging.info(f"Lobby server notified of game end for room {room_id}.")
                else:
                    logging.warning(f"Lobby server response: {response}")
    except Exception as e:
        logging.error(f"Failed to notify lobby server of game end: {e}")

def game_loop(clients: list, input_queue: queue.Queue, game_p1: TetrisGame, game_p2: TetrisGame, 
              p1_user: str, p2_user: str, room_id: int):
    """Runs gravity, processes inputs, and broadcasts state."""
    logging.info("Game loop started for 'Lines Over Time' mode.")
    start_time = time.time()
    game_duration = GAME_DURATION_SECONDS
    winner = None

    last_gravity_tick_time = time.time()
    last_broadcast_time = 0

    while winner is None:
        current_time = time.time()
        elapsed_time = current_time - start_time

        # 1. Check for game end conditions
        if elapsed_time >= game_duration:
            break  # Time's up, exit loop to determine winner by lines

        if game_p1.game_over:
            winner = "P2"
            break
        if game_p2.game_over:
            winner = "P1"
            break

        # 2. Process Inputs
        try:
            while not input_queue.empty():
                player_id, action = input_queue.get_nowait()
                
                if action == "DISCONNECT" or action == "FORFEIT":
                    logging.info(f"Player {player_id + 1} disconnected or forfeited.")
                    winner = "P2" if player_id == 0 else "P1"
                    break

                if player_id == 0:
                    process_input(game_p1, action)
                elif player_id == 1:
                    process_input(game_p2, action)

        except queue.Empty:
            pass
        
        if winner:
            break

        # 3. Apply gravity (Tick) with correct timing
        if (current_time - last_gravity_tick_time) * 1000 >= GRAVITY_INTERVAL_MS:
            game_p1.tick()
            game_p2.tick()
            last_gravity_tick_time = current_time

        # 4. Broadcast State periodically
        if current_time - last_broadcast_time > 0.1:  # Broadcast every 100ms
            remaining_time = max(0, int(game_duration - elapsed_time))
            broadcast_state(clients, game_p1, game_p2, remaining_time)
            last_broadcast_time = current_time
            
        time.sleep(0.01)

    # --- Loop has ended, determine the final winner ---
    reason = ""
    loser_username = None
    if winner is None:  # This means time ran out
        score_p1 = game_p1.score
        score_p2 = game_p2.score
        logging.info(f"Time's up! Final score P1:{score_p1} vs P2:{score_p2}")
        reason = "time_up"
        if score_p1 > score_p2:
            winner = "P1"
            loser_username = p2_user
        elif score_p2 > score_p1:
            winner = "P2"
            loser_username = p1_user
        else:
            winner = "TIE"
            reason = "tie"
    else:
        # This means someone topped out or forfeited
        if game_p1.game_over or game_p2.game_over:
            reason = "board_full"
            loser_username = p1_user if game_p1.game_over else p2_user
        else:
            reason = "forfeit"
            loser_username = p1_user if winner == "P2" else p2_user

    # Force both games to be "over" so the final board state is accurate
    game_p1.game_over = True
    game_p2.game_over = True

    handle_game_end(clients, game_p1, game_p2, winner, reason, loser_username, p1_user, p2_user, room_id, start_time)

def find_free_port(start_port: int) -> int:
    """Finds an available TCP port, starting from start_port."""
    port = start_port
    while port < 65535:
        try:
            # Try to bind to the port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                # If bind succeeds, the port is free
                return port
        except OSError:
            # Port is already in use
            port += 1
    raise RuntimeError("Could not find a free port")

# Old main() function removed - server mode is now handled in if __name__ == "__main__" block below

# ============================================================================
# GAME CLIENT (For players to launch from downloaded file)
# ============================================================================

def _notify_lobby_leave_room(room_id: int):
    """Notify lobby server that player is leaving the room."""
    if not room_id:
        return
    try:
        from common import config
        lobby_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lobby_sock.settimeout(2.0)
        lobby_sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
        request = {
            "action": "leave_room",
            "data": {"room_id": room_id}
        }
        request_bytes = json.dumps(request).encode('utf-8')
        protocol.send_msg(lobby_sock, request_bytes)
        # Wait for response
        response_bytes = protocol.recv_msg(lobby_sock)
        lobby_sock.close()
        logging.info(f"Notified lobby server of room leave for room {room_id}")
    except Exception as e:
        logging.warning(f"Failed to notify lobby server of room leave: {e}")

def run_game_client(game_host: str, game_port: int, room_id: int = None):
    """
    Runs the game client GUI.
    This function is called by player_client.py when GAME_START is received.
    It reuses the GUI code from client/client_gui.py.
    """
    # Add project root to path to access client modules
    # Use the same project_root that was found at module load time
    # If not found, search for it
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    
    # Try to find project root by looking for common/ directory
    search_dir = current_dir
    for _ in range(5):  # Go up at most 5 levels
        if os.path.exists(os.path.join(search_dir, "common")):
            project_root = search_dir
            break
        search_dir = os.path.dirname(search_dir)
    
    if project_root and project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    if not project_root:
        logging.error("Could not find project root (looking for 'common' directory)")
        return
    
    try:
        # Import GUI functions from client/client_gui.py
        import importlib.util
        client_gui_path = os.path.join(project_root, "client", "client_gui.py")
        
        if not os.path.exists(client_gui_path):
            # Fallback: try to import directly
            from client import client_gui
            client_gui_module = client_gui
        else:
            spec = importlib.util.spec_from_file_location("client_gui", client_gui_path)
            client_gui_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(client_gui_module)
        
        # Use the game client GUI from client_gui.py
        # We'll create a simplified version that just runs the game
        import pygame
        
        # Initialize pygame
        pygame.init()
        pygame.font.init()
        
        # Set up screen
        screen = pygame.display.set_mode((900, 700))
        pygame.display.set_caption("Tetris Game")
        clock = pygame.time.Clock()
        
        # Connect to game server
        game_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Retry connection
        max_retries = 5
        retry_delay = 0.5
        connected = False
        for attempt in range(max_retries):
            try:
                game_sock.settimeout(2.0)
                game_sock.connect((game_host, game_port))
                game_sock.settimeout(None)
                connected = True
                logging.info(f"Connected to game server at {game_host}:{game_port}")
                break
            except (socket.error, ConnectionRefusedError, OSError) as e:
                if attempt < max_retries - 1:
                    logging.info(f"Connection attempt {attempt + 1} failed, retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logging.error(f"Failed to connect to game server: {e}")
                    pygame.quit()
                    return
        
        if not connected:
            return
        
        # Receive WELCOME message
        welcome_bytes = protocol.recv_msg(game_sock)
        if not welcome_bytes:
            logging.error("Game server disconnected")
            game_sock.close()
            pygame.quit()
            return
        
        welcome_msg = json.loads(welcome_bytes.decode('utf-8'))
        my_role = welcome_msg.get("role")
        logging.info(f"Received WELCOME, my role: {my_role}")
        
        # Set up game state
        last_game_state = None
        game_over_results = None
        game_send_queue = queue.Queue()
        running = True
        user_acknowledged_game_over = False
        game_over_start_time = None  # Track when game over screen started
        my_role = None  # Will be set from WELCOME message
        
        # Load fonts (reuse from client_gui)
        CONFIG = client_gui_module.CONFIG
        font_path = CONFIG["FONTS"]["DEFAULT_FONT"]
        sizes = CONFIG["FONTS"]["SIZES"]
        fonts = {}
        try:
            fonts["TINY"] = pygame.font.Font(font_path, sizes["TINY"])
            fonts["SMALL"] = pygame.font.Font(font_path, sizes["SMALL"])
            fonts["MEDIUM"] = pygame.font.Font(font_path, sizes["MEDIUM"])
            fonts["LARGE"] = pygame.font.Font(font_path, sizes["LARGE"])
            fonts["GAME_OVER"] = pygame.font.Font(font_path, sizes["GAME_OVER"])
        except:
            fonts["TINY"] = pygame.font.Font(None, sizes["TINY"])
            fonts["SMALL"] = pygame.font.Font(None, sizes["SMALL"])
            fonts["MEDIUM"] = pygame.font.Font(None, sizes["MEDIUM"])
            fonts["LARGE"] = pygame.font.Font(None, sizes["LARGE"])
            fonts["GAME_OVER"] = pygame.font.Font(None, sizes["GAME_OVER"])
        
        # UI elements
        ui_elements = {
            "back_to_lobby_btn": client_gui_module.Button(350, 450, 200, 50, fonts["SMALL"], "Back to Lobby")
        }
        
        # Game network thread
        def game_network_thread():
            nonlocal last_game_state, game_over_results, running, my_role
            try:
                while running:
                    readable, _, exceptional = select.select([game_sock], [], [game_sock], 0.1)
                    
                    if exceptional:
                        break
                    
                    if game_sock in readable:
                        data_bytes = protocol.recv_msg(game_sock)
                        if data_bytes is None:
                            break
                        
                        snapshot = json.loads(data_bytes.decode('utf-8'))
                        msg_type = snapshot.get("type")
                        
                        if msg_type == "SNAPSHOT":
                            last_game_state = snapshot
                        elif msg_type == "GAME_OVER":
                            game_over_results = snapshot
                            logging.info(f"Received GAME_OVER: {snapshot}")
                            # Don't break - keep thread running to handle cleanup
                            # The main loop will handle displaying the game over screen
                    
                    # Send messages
                    try:
                        while not game_send_queue.empty():
                            request = game_send_queue.get_nowait()
                            json_bytes = json.dumps(request).encode('utf-8')
                            protocol.send_msg(game_sock, json_bytes)
                    except queue.Empty:
                        pass
            except Exception as e:
                logging.error(f"Error in game network thread: {e}")
            finally:
                if game_sock:
                    game_sock.close()
        
        # Start network thread
        network_thread = threading.Thread(target=game_network_thread, daemon=True)
        network_thread.start()
        
        # Main game loop
        while running:
            # Check if game over and 3 seconds have passed
            if game_over_results:
                if game_over_start_time is None:
                    game_over_start_time = time.time()
                elif time.time() - game_over_start_time >= 3.0:
                    # 3 seconds have passed, allow exit
                    user_acknowledged_game_over = True
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if game_over_results:
                        # After 3 seconds, ESC or button click can exit
                        if user_acknowledged_game_over and event.key == pygame.K_ESCAPE:
                            running = False
                    else:
                        if event.key == pygame.K_LEFT:
                            game_send_queue.put({"type": "INPUT", "action": "MOVE_LEFT"})
                        elif event.key == pygame.K_RIGHT:
                            game_send_queue.put({"type": "INPUT", "action": "MOVE_RIGHT"})
                        elif event.key == pygame.K_DOWN:
                            game_send_queue.put({"type": "INPUT", "action": "SOFT_DROP"})
                        elif event.key == pygame.K_UP:
                            game_send_queue.put({"type": "INPUT", "action": "ROTATE"})
                        elif event.key == pygame.K_SPACE:
                            game_send_queue.put({"type": "INPUT", "action": "HARD_DROP"})
                        elif event.key == pygame.K_ESCAPE:
                            # Send FORFEIT - don't exit yet, wait for GAME_OVER from server
                            game_send_queue.put({"type": "FORFEIT"})
                            # The game server will process FORFEIT, determine winner, 
                            # send GAME_OVER to both players, and notify the lobby server
                
                if game_over_results and user_acknowledged_game_over:
                    if ui_elements["back_to_lobby_btn"].handle_event(event):
                        running = False
            
            # Draw
            screen.fill(CONFIG["COLORS"]["BACKGROUND"])
            
            if game_over_results:
                # Draw game over screen
                if last_game_state:
                    # Draw the final game state first
                    client_gui_module.draw_game_state(screen, fonts, last_game_state, ui_elements)
                # Then draw the game over overlay
                my_state = last_game_state.get("p1_state", {}) if my_role == "P1" else last_game_state.get("p2_state", {}) if last_game_state else {}
                opponent_state = last_game_state.get("p2_state", {}) if my_role == "P1" else last_game_state.get("p1_state", {}) if last_game_state else {}
                client_gui_module.draw_game_over_screen(screen, fonts, ui_elements, game_over_results, my_state, opponent_state)
                
                # Show countdown if less than 3 seconds have passed
                if game_over_start_time and not user_acknowledged_game_over:
                    elapsed = time.time() - game_over_start_time
                    remaining = max(0, 3.0 - elapsed)
                    countdown_text = f"Returning to lobby in {int(remaining) + 1}..."
                    client_gui_module.draw_text(screen, countdown_text, 350, 550, fonts["SMALL"], CONFIG["COLORS"]["TEXT"])
            elif last_game_state:
                # Use the draw_game_state function from client_gui
                client_gui_module.draw_game_state(screen, fonts, last_game_state, ui_elements)
            else:
                client_gui_module.draw_text(screen, "Connecting...", 350, 300, fonts["LARGE"], CONFIG["COLORS"]["TEXT"])
            
            pygame.display.flip()
            clock.tick(CONFIG["TIMING"]["FPS"])
        
        # Wait for network thread
        network_thread.join(timeout=1.0)
        pygame.quit()
        
        # Notify lobby server if game ended normally (not forfeit)
        # The game server already notifies on game_over, but we should also leave the room
        if room_id:
            _notify_lobby_leave_room(room_id)
        
    except Exception as e:
        logging.error(f"Error running game client: {e}", exc_info=True)
        try:
            pygame.quit()
        except:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tetris Game (Server or Client)")
    parser.add_argument('--mode', choices=['server', 'client'], default='server',
                       help='Run as server (default) or client')
    parser.add_argument('--host', type=str, help='Game server host (client mode)')
    parser.add_argument('--port', type=int, help='Game server port (client mode)')
    parser.add_argument('--room_id', type=int, help='Room ID (client mode)')
    parser.add_argument('--p1', type=str, help='Username of Player 1 (server mode)')
    parser.add_argument('--p2', type=str, help='Username of Player 2 (server mode)')
    
    args = parser.parse_args()
    
    if args.mode == 'client':
        if not args.host or not args.port:
            print("Error: --host and --port required for client mode")
            sys.exit(1)
        run_game_client(args.host, args.port, args.room_id)
    else:
        # Server mode (original behavior)
        if not args.p1 or not args.p2 or not args.room_id:
            print("Error: --p1, --p2, and --room_id required for server mode")
            sys.exit(1)
        # Modify main() to accept args
        PORT = args.port if args.port else config.GAME_SERVER_START_PORT
        P1_USERNAME = args.p1
        P2_USERNAME = args.p2
        ROOM_ID = args.room_id
        
        HOST = '0.0.0.0'
        game_seed = random.randint(0, 1_000_000)
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen(2)
            logging.info(f"Tetris Game Server listening on {HOST}:{PORT}...")
        except Exception as e:
            logging.critical(f"Failed to bind socket: {e}")
            sys.exit(1)
        
        clients = []
        client_threads = []
        input_queue = queue.Queue()
        
        try:
            while len(clients) < 2:
                logging.info(f"Waiting for {2 - len(clients)} more player(s)...")
                client_sock, addr = server_socket.accept()
                player_id = len(clients)
                
                clients.append(client_sock)
                logging.info(f"Player {player_id + 1} connected from {addr}.")
                
                role = "P1" if player_id == 0 else "P2"
                welcome_msg = {
                    "type": "WELCOME",
                    "role": role,
                    "seed": game_seed
                }
                try:
                    protocol.send_msg(client_sock, json.dumps(welcome_msg).encode('utf-8'))
                except Exception as e:
                    logging.error(f"Failed to send WELCOME message to {role}: {e}")
                    clients.pop()
                    client_sock.close()
                    continue
                
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_sock, player_id, input_queue),
                    daemon=True
                )
                client_threads.append(thread)
                thread.start()
            
            logging.info("Two players connected. Starting game...")
            game_p1 = TetrisGame(game_seed)
            game_p2 = TetrisGame(game_seed)
            game_loop(clients, input_queue, game_p1, game_p2, P1_USERNAME, P2_USERNAME, ROOM_ID)
        
        except KeyboardInterrupt:
            logging.info("Shutting down game server.")
        except Exception as e:
            logging.error(f"Critical error: {e}", exc_info=True)
        finally:
            for sock in clients:
                sock.close()
            server_socket.close()
            logging.info("Tetris game server shut down.")
