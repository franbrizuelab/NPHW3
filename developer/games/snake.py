#!/usr/bin/env python3
"""
Snake Game Server/Client
A CLI-based multiplayer snake game.
Two players control snakes on the same grid.
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
from datetime import datetime
from collections import deque

# Add project root to path to access common modules
current_dir = os.path.dirname(os.path.abspath(__file__))

# Search upward from current directory to find project root (directory containing "common")
project_root = None
search_dir = current_dir
max_levels = 10
for _ in range(max_levels):
    common_path = os.path.join(search_dir, "common")
    if os.path.exists(common_path) and os.path.isdir(common_path):
        project_root = search_dir
        break
    parent = os.path.dirname(search_dir)
    if parent == search_dir:
        break
    search_dir = parent

if project_root:
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
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
# PARAMETERS - Game Configuration
# ============================================================================

PARAMETERS = {
    # Grid size
    "GRID_WIDTH": 15,
    "GRID_HEIGHT": 15,
    
    # Characters for display
    "BORDER_CHAR": "#",  # Thick border character
    "SNAKE_P1_CHAR": "o",  # Player 1 snake body
    "SNAKE_P2_CHAR": "o",  # Player 2 snake body
    "SNAKE_P1_HEAD": "@",  # Player 1 snake head
    "SNAKE_P2_HEAD": "&",  # Player 2 snake head
    "APPLE_CHAR": "A",  # Apple (or use "A" if emoji doesn't work)
    "EMPTY_CHAR": " ",  # Empty cell
    
    # Game settings
    "INITIAL_SNAKE_LENGTH": 3,
    "GAME_SPEED": 0.1,  # Seconds between moves (lower = faster)
    "APPLE_SPAWN_INTERVAL": 2.0,  # Seconds between apple spawns
    "MAX_APPLES": 3,  # Maximum apples on the board at once
}

# Fallback characters if emoji doesn't work in terminal
FALLBACK_CHARS = {
    "APPLE_CHAR": "A",
    "SNAKE_P1_CHAR": "#",
    "SNAKE_P2_CHAR": "*",
    "SNAKE_P1_HEAD": "@",
    "SNAKE_P2_HEAD": "%",
}

# ============================================================================
# GAME LOGIC
# ============================================================================

class Snake:
    """Represents a snake."""
    
    def __init__(self, start_pos: tuple, direction: str, player_id: int):
        self.body = deque([start_pos])
        self.direction = direction  # 'UP', 'DOWN', 'LEFT', 'RIGHT'
        self.player_id = player_id
        self.alive = True
        self.length = PARAMETERS["INITIAL_SNAKE_LENGTH"]
        
        # Initialize body to initial length
        dx, dy = self._get_direction_offset(self.direction)
        for i in range(1, self.length):
            new_pos = (start_pos[0] - dx * i, start_pos[1] - dy * i)
            self.body.append(new_pos)
    
    def _get_direction_offset(self, direction: str) -> tuple:
        """Get (dx, dy) offset for a direction."""
        offsets = {
            'UP': (0, -1),
            'DOWN': (0, 1),
            'LEFT': (-1, 0),
            'RIGHT': (1, 0)
        }
        return offsets.get(direction, (0, 0))
    
    def change_direction(self, new_direction: str):
        """Change direction (prevent 180-degree turns)."""
        opposite = {
            'UP': 'DOWN',
            'DOWN': 'UP',
            'LEFT': 'RIGHT',
            'RIGHT': 'LEFT'
        }
        if new_direction != opposite.get(self.direction):
            self.direction = new_direction
    
    def move(self, grow: bool = False):
        """Move the snake one step."""
        if not self.alive:
            return
        
        dx, dy = self._get_direction_offset(self.direction)
        head = self.body[0]
        new_head = (head[0] + dx, head[1] + dy)
        
        self.body.appendleft(new_head)
        if not grow:
            self.body.pop()
        else:
            self.length += 1
    
    def get_head(self) -> tuple:
        """Get the head position."""
        return self.body[0] if self.body else None
    
    def get_body_set(self) -> set:
        """Get all body positions as a set."""
        return set(self.body)

class SnakeGame:
    """Main game logic for Snake."""
    
    def __init__(self):
        self.width = PARAMETERS["GRID_WIDTH"]
        self.height = PARAMETERS["GRID_HEIGHT"]
        
        # Initialize snakes at opposite corners
        self.snake1 = Snake((2, 2), 'RIGHT', 0)
        self.snake2 = Snake((self.width - 3, self.height - 3), 'LEFT', 1)
        
        self.apples = []
        self.last_apple_spawn = time.time()
        self.game_over = False
        self.winner = None
        self.turn_count = 0
        
        # Spawn initial apple
        self._spawn_apple()
    
    def _spawn_apple(self):
        """Spawn a new apple at a random empty position."""
        if len(self.apples) >= PARAMETERS["MAX_APPLES"]:
            return
        
        # Find empty positions
        occupied = set()
        occupied.update(self.snake1.get_body_set())
        occupied.update(self.snake2.get_body_set())
        occupied.update(self.apples)
        
        # Try to find an empty spot
        attempts = 0
        while attempts < 100:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            if (x, y) not in occupied:
                self.apples.append((x, y))
                return
            attempts += 1
    
    def process_move(self, player_id: int, direction: str) -> dict:
        """Process a move from a player."""
        if self.game_over:
            return {'success': False, 'message': 'Game is already over'}
        
        snake = self.snake1 if player_id == 0 else self.snake2
        if not snake.alive:
            return {'success': False, 'message': 'Your snake is dead'}
        
        snake.change_direction(direction)
        return {'success': True}
    
    def tick(self):
        """Advance the game by one tick."""
        if self.game_over:
            return
        
        self.turn_count += 1
        
        # Move both snakes
        for snake in [self.snake1, self.snake2]:
            if snake.alive:
                # Check if snake will eat an apple
                head = snake.get_head()
                dx, dy = snake._get_direction_offset(snake.direction)
                next_head = (head[0] + dx, head[1] + dy)
                
                grow = next_head in self.apples
                if grow:
                    self.apples.remove(next_head)
                
                snake.move(grow=grow)
        
        # Check collisions
        self._check_collisions()
        
        # Spawn apples periodically
        current_time = time.time()
        if current_time - self.last_apple_spawn >= PARAMETERS["APPLE_SPAWN_INTERVAL"]:
            self._spawn_apple()
            self.last_apple_spawn = current_time
        
        # Check win condition
        if not self.snake1.alive and not self.snake2.alive:
            self.game_over = True
            self.winner = "TIE"
        elif not self.snake1.alive:
            self.game_over = True
            self.winner = "P2"
        elif not self.snake2.alive:
            self.game_over = True
            self.winner = "P1"
    
    def _check_collisions(self):
        """Check for collisions with borders and other snakes."""
        # Check snake1
        if self.snake1.alive:
            head = self.snake1.get_head()
            # Border collision
            if head[0] <= 0 or head[0] >= self.width - 1 or head[1] <= 0 or head[1] >= self.height - 1:
                self.snake1.alive = False
            # Self collision (head touches body)
            elif head in list(self.snake1.body)[1:]:
                self.snake1.alive = False
            # Collision with snake2
            elif head in self.snake2.get_body_set():
                self.snake1.alive = False
        
        # Check snake2
        if self.snake2.alive:
            head = self.snake2.get_head()
            # Border collision
            if head[0] <= 0 or head[0] >= self.width - 1 or head[1] <= 0 or head[1] >= self.height - 1:
                self.snake2.alive = False
            # Self collision
            elif head in list(self.snake2.body)[1:]:
                self.snake2.alive = False
            # Collision with snake1
            elif head in self.snake1.get_body_set():
                self.snake2.alive = False
    
    def get_state(self) -> dict:
        """Get current game state."""
        return {
            'width': self.width,
            'height': self.height,
            'snake1': {
                'body': list(self.snake1.body),
                'alive': self.snake1.alive,
                'length': self.snake1.length
            },
            'snake2': {
                'body': list(self.snake2.body),
                'alive': self.snake2.alive,
                'length': self.snake2.length
            },
            'apples': self.apples[:],
            'game_over': self.game_over,
            'winner': self.winner,
            'turn_count': self.turn_count
        }
    
    def print_board(self):
        """Print the board to stdout (for CLI)."""
        state = self.get_state()
        width = state['width']
        height = state['height']
        
        # Create grid
        grid = [[PARAMETERS["EMPTY_CHAR"] for _ in range(width)] for _ in range(height)]
        
        # Draw borders
        for y in range(height):
            grid[y][0] = PARAMETERS["BORDER_CHAR"]
            grid[y][width - 1] = PARAMETERS["BORDER_CHAR"]
        for x in range(width):
            grid[0][x] = PARAMETERS["BORDER_CHAR"]
            grid[height - 1][x] = PARAMETERS["BORDER_CHAR"]
        
        # Draw apples
        for apple_x, apple_y in state['apples']:
            if 0 < apple_y < height - 1 and 0 < apple_x < width - 1:
                grid[apple_y][apple_x] = PARAMETERS["APPLE_CHAR"]
        
        # Draw snake1
        if state['snake1']['alive']:
            body = state['snake1']['body']
            for i, (x, y) in enumerate(body):
                if 0 < y < height - 1 and 0 < x < width - 1:
                    if i == 0:  # Head
                        grid[y][x] = PARAMETERS["SNAKE_P1_HEAD"]
                    else:
                        grid[y][x] = PARAMETERS["SNAKE_P1_CHAR"]
        
        # Draw snake2
        if state['snake2']['alive']:
            body = state['snake2']['body']
            for i, (x, y) in enumerate(body):
                if 0 < y < height - 1 and 0 < x < width - 1:
                    if i == 0:  # Head
                        grid[y][x] = PARAMETERS["SNAKE_P2_HEAD"]
                    else:
                        grid[y][x] = PARAMETERS["SNAKE_P2_CHAR"]
        
        # Print grid
        print("\n" + "=" * (width * 2))
        for row in grid:
            print("".join(row))
        print("=" * (width * 2))
        
        # Print status
        print(f"Snake 1 (P1): Length {state['snake1']['length']}, Alive: {state['snake1']['alive']}")
        print(f"Snake 2 (P2): Length {state['snake2']['length']}, Alive: {state['snake2']['alive']}")
        print(f"Apples: {len(state['apples'])}")

# ============================================================================
# GAME SERVER
# ============================================================================

def handle_client(sock: socket.socket, player_id: int, input_queue: queue.Queue):
    """Handle a client connection."""
    player_symbol = 'P1' if player_id == 0 else 'P2'
    logging.info(f"Client thread started for Player {player_id + 1} ({player_symbol}).")
    
    try:
        while True:
            data_bytes = protocol.recv_msg(sock)
            if data_bytes is None:
                logging.warning(f"Player {player_id + 1} disconnected.")
                input_queue.put((player_id, "DISCONNECT"))
                break
            
            try:
                request = json.loads(data_bytes.decode('utf-8'))
                if request.get("type") == "MOVE":
                    direction = request.get("direction")
                    if direction in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
                        input_queue.put((player_id, "MOVE", direction))
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

def game_loop(clients: list, input_queue: queue.Queue, p1_user: str, p2_user: str, room_id: int):
    """Main game loop."""
    game = SnakeGame()
    logging.info("Snake game started")
    
    last_tick_time = time.time()
    
    # Send initial state
    state_msg = {
        "type": "STATE",
        "state": game.get_state()
    }
    for sock in clients:
        if sock:
            protocol.send_msg(sock, json.dumps(state_msg).encode('utf-8'))
    
    while not game.game_over:
        current_time = time.time()
        
        # Process inputs
        try:
            while not input_queue.empty():
                item = input_queue.get_nowait()
                player_id = item[0]
                action = item[1]
                
                if action == "DISCONNECT" or action == "FORFEIT":
                    winner = "P2" if player_id == 0 else "P1"
                    loser = p1_user if player_id == 0 else p2_user
                    reason = "forfeit" if action == "FORFEIT" else "disconnect"
                    handle_game_end(clients, game, winner, reason, loser, p1_user, p2_user, room_id, time.time())
                    return
                
                if action == "MOVE":
                    direction = item[2]
                    game.process_move(player_id, direction)
        except queue.Empty:
            pass
        
        # Game tick at specified speed
        if current_time - last_tick_time >= PARAMETERS["GAME_SPEED"]:
            game.tick()
            last_tick_time = current_time
            
            # Broadcast updated state
            state_msg = {
                "type": "STATE",
                "state": game.get_state()
            }
            for sock in clients:
                if sock:
                    protocol.send_msg(sock, json.dumps(state_msg).encode('utf-8'))
            
            if game.game_over:
                winner = "P1" if game.winner == "P1" else ("P2" if game.winner == "P2" else "TIE")
                loser = None if game.winner == "TIE" else (p2_user if game.winner == "P1" else p1_user)
                reason = "win" if game.winner != "TIE" else "tie"
                handle_game_end(clients, game, winner, reason, loser, p1_user, p2_user, room_id, time.time())
                return
        
        time.sleep(0.05)  # Small sleep to prevent CPU spinning

def handle_game_end(clients: list, game: SnakeGame, winner: str, reason: str, 
                   loser_username: str, p1_user: str, p2_user: str, room_id: int, start_time: float):
    """Handle game end."""
    logging.info(f"Game ended. Winner: {winner}, Reason: {reason}")
    
    # Send GAME_OVER to clients
    game_over_msg = {
        "type": "GAME_OVER",
        "winner": winner,
        "winner_username": p1_user if winner == "P1" else (p2_user if winner == "P2" else "TIE"),
        "reason": reason,
        "loser_username": loser_username,
        "room_id": room_id,
        "final_state": game.get_state()
    }
    
    try:
        for sock in list(clients):
            if sock:
                protocol.send_msg(sock, json.dumps(game_over_msg).encode('utf-8'))
    except Exception as e:
        logging.warning(f"Failed to send GAME_OVER message: {e}")
    
    # Notify lobby server
    try:
        lobby_request = {
            "action": "game_over",
            "data": {"room_id": room_id}
        }
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as lobby_sock:
            lobby_sock.settimeout(5.0)
            lobby_sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
            request_bytes = json.dumps(lobby_request).encode('utf-8')
            protocol.send_msg(lobby_sock, request_bytes)
            response_bytes = protocol.recv_msg(lobby_sock)
            if response_bytes:
                response = json.loads(response_bytes.decode('utf-8'))
                if response.get("status") == "ok":
                    logging.info(f"Lobby server notified of game end for room {room_id}.")
    except Exception as e:
        logging.error(f"Failed to notify lobby server of game end: {e}")

# ============================================================================
# GAME CLIENT (CLI)
# ============================================================================

def run_game_client(game_host: str, game_port: int, room_id: int = None):
    """Run the game client in CLI mode."""
    try:
        # Connect to game server
        game_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        max_retries = 5
        retry_delay = 0.5
        connected = False
        for attempt in range(max_retries):
            try:
                game_sock.settimeout(2.0)
                game_sock.connect((game_host, game_port))
                game_sock.settimeout(None)
                connected = True
                print(f"Connected to game server at {game_host}:{game_port}")
                break
            except (socket.error, ConnectionRefusedError, OSError) as e:
                if attempt < max_retries - 1:
                    print(f"Connection attempt {attempt + 1} failed, retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    print(f"Failed to connect to game server: {e}")
                    return
        
        if not connected:
            return
        
        # Receive WELCOME message
        welcome_bytes = protocol.recv_msg(game_sock)
        if not welcome_bytes:
            print("Game server disconnected")
            game_sock.close()
            return
        
        welcome_msg = json.loads(welcome_bytes.decode('utf-8'))
        my_role = welcome_msg.get("role")
        my_player_id = 0 if my_role == "P1" else 1
        print(f"You are {my_role}")
        print("\nControls: W=UP, S=DOWN, A=LEFT, D=RIGHT, Q=QUIT")
        print("=" * 60)
        
        # Game state
        current_state = None
        game_over = False
        
        # Network thread
        def network_thread():
            nonlocal current_state, game_over
            try:
                while not game_over:
                    data_bytes = protocol.recv_msg(game_sock)
                    if data_bytes is None:
                        break
                    
                    msg = json.loads(data_bytes.decode('utf-8'))
                    msg_type = msg.get("type")
                    
                    if msg_type == "STATE":
                        current_state = msg.get("state")
                        _print_board_cli(current_state, my_player_id)
                    elif msg_type == "GAME_OVER":
                        game_over = True
                        winner = msg.get("winner_username", "Unknown")
                        reason = msg.get("reason", "unknown")
                        final_state = msg.get("final_state", {})
                        _print_board_cli(final_state, my_player_id)
                        print(f"\n{'='*60}")
                        print(f"GAME OVER!")
                        print(f"Winner: {winner}")
                        print(f"Reason: {reason}")
                        print(f"{'='*60}\n")
                        break
            except Exception as e:
                print(f"Error in network thread: {e}")
            finally:
                game_sock.close()
        
        def _print_board_cli(state: dict, player_id: int):
            """Print the game board to CLI."""
            width = state.get('width', PARAMETERS["GRID_WIDTH"])
            height = state.get('height', PARAMETERS["GRID_HEIGHT"])
            
            # Create grid
            grid = [[PARAMETERS["EMPTY_CHAR"] for _ in range(width)] for _ in range(height)]
            
            # Draw borders
            for y in range(height):
                grid[y][0] = PARAMETERS["BORDER_CHAR"]
                grid[y][width - 1] = PARAMETERS["BORDER_CHAR"]
            for x in range(width):
                grid[0][x] = PARAMETERS["BORDER_CHAR"]
                grid[height - 1][x] = PARAMETERS["BORDER_CHAR"]
            
            # Draw apples
            for apple_x, apple_y in state.get('apples', []):
                if 0 < apple_y < height - 1 and 0 < apple_x < width - 1:
                    grid[apple_y][apple_x] = PARAMETERS["APPLE_CHAR"]
            
            # Draw snake1
            snake1 = state.get('snake1', {})
            if snake1.get('alive', False):
                body = snake1.get('body', [])
                for i, (x, y) in enumerate(body):
                    if 0 < y < height - 1 and 0 < x < width - 1:
                        if i == 0:
                            grid[y][x] = PARAMETERS["SNAKE_P1_HEAD"]
                        else:
                            grid[y][x] = PARAMETERS["SNAKE_P1_CHAR"]
            
            # Draw snake2
            snake2 = state.get('snake2', {})
            if snake2.get('alive', False):
                body = snake2.get('body', [])
                for i, (x, y) in enumerate(body):
                    if 0 < y < height - 1 and 0 < x < width - 1:
                        if i == 0:
                            grid[y][x] = PARAMETERS["SNAKE_P2_HEAD"]
                        else:
                            grid[y][x] = PARAMETERS["SNAKE_P2_CHAR"]
            
            # Clear screen and print
            print("\033[2J\033[H")  # Clear screen and move cursor to top
            print("=" * (width * 2))
            for row in grid:
                print("".join(row))
            print("=" * (width * 2))
            
            # Print status
            print(f"P1 Snake: Length {snake1.get('length', 0)}, Alive: {snake1.get('alive', False)}")
            print(f"P2 Snake: Length {snake2.get('length', 0)}, Alive: {snake2.get('alive', False)}")
            print(f"Apples: {len(state.get('apples', []))}")
            if state.get('game_over'):
                print(f"Game Over! Winner: {state.get('winner', 'Unknown')}")
        
        # Start network thread
        net_thread = threading.Thread(target=network_thread, daemon=True)
        net_thread.start()
        
        # Main input loop
        import select
        import tty
        import termios
        
        # Set terminal to raw mode for immediate key input
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            
            print("\nGame started! Use WASD to move, Q to quit...")
            while not game_over:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1).lower()
                    
                    if key == 'q':
                        forfeit_msg = {"type": "FORFEIT"}
                        protocol.send_msg(game_sock, json.dumps(forfeit_msg).encode('utf-8'))
                        break
                    elif key == 'w':
                        move_msg = {"type": "MOVE", "direction": "UP"}
                        protocol.send_msg(game_sock, json.dumps(move_msg).encode('utf-8'))
                    elif key == 's':
                        move_msg = {"type": "MOVE", "direction": "DOWN"}
                        protocol.send_msg(game_sock, json.dumps(move_msg).encode('utf-8'))
                    elif key == 'a':
                        move_msg = {"type": "MOVE", "direction": "LEFT"}
                        protocol.send_msg(game_sock, json.dumps(move_msg).encode('utf-8'))
                    elif key == 'd':
                        move_msg = {"type": "MOVE", "direction": "RIGHT"}
                        protocol.send_msg(game_sock, json.dumps(move_msg).encode('utf-8'))
                
                time.sleep(0.05)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        
        # Wait for network thread
        net_thread.join(timeout=2.0)
        print("\nGame client exiting.")
        
    except Exception as e:
        print(f"Error running game client: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Snake Game (Server or Client)")
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
        # Server mode
        if not args.p1 or not args.p2 or not args.room_id:
            print("Error: --p1, --p2, and --room_id required for server mode")
            sys.exit(1)
        
        PORT = args.port if args.port else config.GAME_SERVER_START_PORT
        P1_USERNAME = args.p1
        P2_USERNAME = args.p2
        ROOM_ID = args.room_id
        
        HOST = '0.0.0.0'
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen(2)
            logging.info(f"Snake Game Server listening on {HOST}:{PORT}...")
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
                    "role": role
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
            game_loop(clients, input_queue, P1_USERNAME, P2_USERNAME, ROOM_ID)
        
        except KeyboardInterrupt:
            logging.info("Shutting down game server.")
        except Exception as e:
            logging.error(f"Critical error: {e}", exc_info=True)
        finally:
            for sock in clients:
                sock.close()
            server_socket.close()
            logging.info("Snake game server shut down.")
