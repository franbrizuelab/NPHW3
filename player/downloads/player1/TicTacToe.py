#!/usr/bin/env python3
"""
Tic-Tac-Toe Game Server/Client
A simple CLI-based game for testing the game platform.
Can run as server or client mode.
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
# GAME LOGIC
# ============================================================================

class TicTacToeGame:
    """Simple Tic-Tac-Toe game logic."""
    
    def __init__(self):
        self.board = [[' ' for _ in range(3)] for _ in range(3)]
        self.current_player = 'X'  # X goes first
        self.game_over = False
        self.winner = None
        self.move_count = 0
    
    def make_move(self, row: int, col: int, player: str) -> dict:
        """Make a move. Returns {'success': bool, 'message': str}."""
        if self.game_over:
            return {'success': False, 'message': 'Game is already over'}
        
        if player != self.current_player:
            return {'success': False, 'message': f'Not {player}\'s turn'}
        
        if not (0 <= row < 3 and 0 <= col < 3):
            return {'success': False, 'message': 'Invalid position'}
        
        if self.board[row][col] != ' ':
            return {'success': False, 'message': 'Position already taken'}
        
        self.board[row][col] = player
        self.move_count += 1
        
        # Check for win
        if self._check_win(row, col, player):
            self.game_over = True
            self.winner = player
            return {'success': True, 'message': f'{player} wins!', 'game_over': True, 'winner': player}
        
        # Check for tie
        if self.move_count >= 9:
            self.game_over = True
            self.winner = 'TIE'
            return {'success': True, 'message': 'Tie game!', 'game_over': True, 'winner': 'TIE'}
        
        # Switch player
        self.current_player = 'O' if player == 'X' else 'X'
        return {'success': True, 'message': f'{player} played ({row}, {col})'}
    
    def _check_win(self, row: int, col: int, player: str) -> bool:
        """Check if the last move resulted in a win."""
        # Check row
        if all(self.board[row][c] == player for c in range(3)):
            return True
        # Check column
        if all(self.board[r][col] == player for r in range(3)):
            return True
        # Check diagonal (top-left to bottom-right)
        if row == col and all(self.board[i][i] == player for i in range(3)):
            return True
        # Check anti-diagonal (top-right to bottom-left)
        if row + col == 2 and all(self.board[i][2-i] == player for i in range(3)):
            return True
        return False
    
    def get_state(self) -> dict:
        """Get current game state."""
        return {
            'board': [row[:] for row in self.board],  # Copy board
            'current_player': self.current_player,
            'game_over': self.game_over,
            'winner': self.winner,
            'move_count': self.move_count
        }
    
    def print_board(self):
        """Print the board to stdout (for CLI)."""
        print("\n  0   1   2")
        for i, row in enumerate(self.board):
            print(f"{i} {row[0]} | {row[1]} | {row[2]}")
            if i < 2:
                print("  ---------")

# ============================================================================
# GAME SERVER
# ============================================================================

def handle_client(sock: socket.socket, player_id: int, input_queue: queue.Queue):
    """Handle a client connection."""
    player_symbol = 'X' if player_id == 0 else 'O'
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
                    row = request.get("row")
                    col = request.get("col")
                    if row is not None and col is not None:
                        input_queue.put((player_id, "MOVE", row, col))
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
    game = TicTacToeGame()
    logging.info("Tic-Tac-Toe game started")
    
    # Send initial state
    state_msg = {
        "type": "STATE",
        "state": game.get_state()
    }
    for sock in clients:
        if sock:
            protocol.send_msg(sock, json.dumps(state_msg).encode('utf-8'))
    
    while not game.game_over:
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
                    row = item[2]
                    col = item[3]
                    player_symbol = 'X' if player_id == 0 else 'O'
                    result = game.make_move(row, col, player_symbol)
                    
                    if result['success']:
                        # Broadcast updated state
                        state_msg = {
                            "type": "STATE",
                            "state": game.get_state()
                        }
                        for sock in clients:
                            if sock:
                                protocol.send_msg(sock, json.dumps(state_msg).encode('utf-8'))
                        
                        if game.game_over:
                            winner = "P1" if game.winner == 'X' else ("P2" if game.winner == 'O' else "TIE")
                            loser = None if game.winner == 'TIE' else (p2_user if game.winner == 'X' else p1_user)
                            reason = "win" if game.winner != 'TIE' else "tie"
                            handle_game_end(clients, game, winner, reason, loser, p1_user, p2_user, room_id, time.time())
                            return
        except queue.Empty:
            pass
        
        time.sleep(0.1)

def handle_game_end(clients: list, game: TicTacToeGame, winner: str, reason: str, 
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
        my_symbol = 'X' if my_role == "P1" else 'O'
        print(f"You are {my_role} ({my_symbol})")
        
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
                        # Print board
                        board = current_state.get("board", [])
                        print("\nCurrent board:")
                        print("  0   1   2")
                        for i, row in enumerate(board):
                            print(f"{i} {row[0]} | {row[1]} | {row[2]}")
                            if i < 2:
                                print("  ---------")
                        if not current_state.get("game_over"):
                            print(f"\nCurrent player: {current_state.get('current_player')}")
                            if current_state.get("current_player") == my_symbol:
                                print("It's your turn! Enter row and column (0-2): ")
                    elif msg_type == "GAME_OVER":
                        game_over = True
                        winner = msg.get("winner_username", "Unknown")
                        reason = msg.get("reason", "unknown")
                        print(f"\n{'='*40}")
                        print(f"GAME OVER!")
                        print(f"Winner: {winner}")
                        print(f"Reason: {reason}")
                        print(f"{'='*40}\n")
                        break
            except Exception as e:
                print(f"Error in network thread: {e}")
            finally:
                game_sock.close()
        
        # Start network thread
        net_thread = threading.Thread(target=network_thread, daemon=True)
        net_thread.start()
        
        # Main input loop
        print("\nGame started! Waiting for your turn...")
        while not game_over:
            if current_state and current_state.get("current_player") == my_symbol and not current_state.get("game_over"):
                try:
                    user_input = input().strip()
                    if user_input.lower() == 'quit' or user_input.lower() == 'q':
                        # Send forfeit
                        forfeit_msg = {"type": "FORFEIT"}
                        protocol.send_msg(game_sock, json.dumps(forfeit_msg).encode('utf-8'))
                        break
                    
                    parts = user_input.split()
                    if len(parts) == 2:
                        row = int(parts[0])
                        col = int(parts[1])
                        move_msg = {"type": "MOVE", "row": row, "col": col}
                        protocol.send_msg(game_sock, json.dumps(move_msg).encode('utf-8'))
                    else:
                        print("Invalid input. Use: row col (e.g., '1 2') or 'quit' to forfeit")
                except (ValueError, KeyboardInterrupt):
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"Error: {e}")
            else:
                time.sleep(0.1)
        
        # Wait for network thread
        net_thread.join(timeout=2.0)
        print("Game client exiting.")
        
    except Exception as e:
        print(f"Error running game client: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tic-Tac-Toe Game (Server or Client)")
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
            logging.info(f"Tic-Tac-Toe Game Server listening on {HOST}:{PORT}...")
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
            logging.info("Tic-Tac-Toe game server shut down.")
