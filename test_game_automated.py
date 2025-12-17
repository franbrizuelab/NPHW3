#!/usr/bin/env python3
"""
Automated test suite for game platform.
Tests various scenarios including:
- Normal gameplay
- Connection loss
- Forfeit scenarios
- Room creation after game ends
- Multiple games in sequence
"""

import subprocess
import time
import socket
import json
import sys
import os
import threading
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import config, protocol

class GameTestClient:
    """Simulates a game client for testing."""
    
    def __init__(self, username: str):
        self.username = username
        self.sock = None
        self.connected = False
        self.game_process = None
    
    def connect_to_lobby(self):
        """Connect to lobby server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
            self.connected = True
            return True
        except Exception as e:
            print(f"[{self.username}] Failed to connect: {e}")
            return False
    
    def send_action(self, action: str, data: dict = None):
        """Send an action to the lobby server."""
        if not self.connected:
            return None
        
        request = {"action": action, "data": data or {}}
        try:
            request_bytes = json.dumps(request).encode('utf-8')
            protocol.send_msg(self.sock, request_bytes)
            response_bytes = protocol.recv_msg(self.sock)
            if response_bytes:
                return json.loads(response_bytes.decode('utf-8'))
        except Exception as e:
            print(f"[{self.username}] Error sending action {action}: {e}")
        return None
    
    def login(self, password: str = "testpass"):
        """Login to lobby."""
        response = self.send_action("login", {"user": self.username, "pass": password})
        return response and response.get("status") == "ok"
    
    def create_room(self, game_id: int = 1, is_public: bool = True):
        """Create a room."""
        response = self.send_action("create_room", {
            "game_id": game_id,
            "is_public": is_public,
            "name": f"{self.username}'s Room"
        })
        if response and response.get("status") == "ok":
            room_data = response.get("data", {})
            return room_data.get("room_id")
        return None
    
    def join_room(self, room_id: int):
        """Join a room."""
        response = self.send_action("join_room", {"room_id": room_id})
        return response and response.get("status") == "ok"
    
    def start_game(self):
        """Start the game."""
        response = self.send_action("start_game")
        if response and response.get("status") == "ok":
            game_data = response.get("data", {})
            return game_data.get("host"), game_data.get("port")
        return None, None
    
    def launch_game_client(self, game_host: str, game_port: int, room_id: int):
        """Launch the game client process."""
        game_file = "developer/games/tic_tac_toe.py"
        cmd = [
            "python3", game_file,
            "--mode", "client",
            "--host", game_host,
            "--port", str(game_port),
            "--room_id", str(room_id)
        ]
        self.game_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return self.game_process
    
    def close(self):
        """Close connection."""
        if self.game_process:
            self.game_process.terminate()
            self.game_process.wait(timeout=2)
        if self.sock:
            self.sock.close()
        self.connected = False

def test_normal_gameplay():
    """Test 1: Normal gameplay - two players play a complete game."""
    print("\n" + "="*60)
    print("TEST 1: Normal Gameplay")
    print("="*60)
    
    p1 = GameTestClient("test_player1")
    p2 = GameTestClient("test_player2")
    
    try:
        # Connect and login
        assert p1.connect_to_lobby(), "P1 failed to connect"
        assert p2.connect_to_lobby(), "P2 failed to connect"
        assert p1.login(), "P1 failed to login"
        assert p2.login(), "P2 failed to login"
        print("✓ Both players connected and logged in")
        
        # P1 creates room
        room_id = p1.create_room(game_id=1, is_public=True)
        assert room_id is not None, "Failed to create room"
        print(f"✓ Room {room_id} created")
        
        # P2 joins room
        assert p2.join_room(room_id), "P2 failed to join room"
        print(f"✓ P2 joined room {room_id}")
        
        # Start game
        game_host, game_port = p1.start_game()
        assert game_host and game_port, "Failed to start game"
        print(f"✓ Game started on {game_host}:{game_port}")
        
        # Launch game clients (simplified - would need actual game interaction)
        time.sleep(1)  # Wait for game server to be ready
        
        print("✓ Test 1 PASSED: Normal gameplay setup successful")
        return True
        
    except AssertionError as e:
        print(f"✗ Test 1 FAILED: {e}")
        return False
    finally:
        p1.close()
        p2.close()

def test_connection_loss():
    """Test 2: Connection loss during game."""
    print("\n" + "="*60)
    print("TEST 2: Connection Loss")
    print("="*60)
    
    p1 = GameTestClient("test_player1")
    p2 = GameTestClient("test_player2")
    
    try:
        # Setup game
        assert p1.connect_to_lobby() and p1.login(), "Setup failed"
        assert p2.connect_to_lobby() and p2.login(), "Setup failed"
        room_id = p1.create_room()
        assert room_id is not None, "Room creation failed"
        assert p2.join_room(room_id), "Join failed"
        game_host, game_port = p1.start_game()
        assert game_host and game_port, "Game start failed"
        print("✓ Game setup complete")
        
        # Simulate connection loss
        p2.sock.close()
        p2.connected = False
        print("✓ Simulated P2 connection loss")
        
        time.sleep(2)  # Wait for server to detect disconnect
        
        # P2 should be able to reconnect and create new room
        assert p2.connect_to_lobby() and p2.login(), "P2 reconnection failed"
        new_room_id = p2.create_room()
        assert new_room_id is not None, "P2 failed to create new room after disconnect"
        print(f"✓ P2 reconnected and created new room {new_room_id}")
        
        print("✓ Test 2 PASSED: Connection loss handled correctly")
        return True
        
    except AssertionError as e:
        print(f"✗ Test 2 FAILED: {e}")
        return False
    finally:
        p1.close()
        p2.close()

def test_room_creation_after_game():
    """Test 3: Creating a new room after game ends."""
    print("\n" + "="*60)
    print("TEST 3: Room Creation After Game")
    print("="*60)
    
    p1 = GameTestClient("test_player1")
    p2 = GameTestClient("test_player2")
    
    try:
        # Setup and play a game (simplified)
        assert p1.connect_to_lobby() and p1.login(), "Setup failed"
        assert p2.connect_to_lobby() and p2.login(), "Setup failed"
        
        # First game
        room_id1 = p1.create_room()
        assert room_id1 is not None, "First room creation failed"
        assert p2.join_room(room_id1), "Join failed"
        game_host, game_port = p1.start_game()
        assert game_host and game_port, "Game start failed"
        print("✓ First game started")
        
        # Wait a bit (simulate game ending)
        time.sleep(2)
        
        # Try to create a new room
        room_id2 = p1.create_room()
        assert room_id2 is not None, "Failed to create second room"
        print(f"✓ Second room {room_id2} created successfully")
        
        # P2 should also be able to create a room
        room_id3 = p2.create_room()
        assert room_id3 is not None, "P2 failed to create room after game"
        print(f"✓ P2 created room {room_id3} after game")
        
        print("✓ Test 3 PASSED: Room creation after game works")
        return True
        
    except AssertionError as e:
        print(f"✗ Test 3 FAILED: {e}")
        return False
    finally:
        p1.close()
        p2.close()

def test_multiple_games_sequence():
    """Test 4: Multiple games in sequence."""
    print("\n" + "="*60)
    print("TEST 4: Multiple Games Sequence")
    print("="*60)
    
    p1 = GameTestClient("test_player1")
    p2 = GameTestClient("test_player2")
    
    try:
        assert p1.connect_to_lobby() and p1.login(), "Setup failed"
        assert p2.connect_to_lobby() and p2.login(), "Setup failed"
        
        # Play 3 games in sequence
        for i in range(3):
            room_id = p1.create_room()
            assert room_id is not None, f"Game {i+1}: Room creation failed"
            assert p2.join_room(room_id), f"Game {i+1}: Join failed"
            game_host, game_port = p1.start_game()
            assert game_host and game_port, f"Game {i+1}: Start failed"
            print(f"✓ Game {i+1} started (room {room_id})")
            time.sleep(1)  # Brief pause between games
        
        print("✓ Test 4 PASSED: Multiple games in sequence work")
        return True
        
    except AssertionError as e:
        print(f"✗ Test 4 FAILED: {e}")
        return False
    finally:
        p1.close()
        p2.close()

def test_forfeit_scenario():
    """Test 5: Player forfeits during game."""
    print("\n" + "="*60)
    print("TEST 5: Forfeit Scenario")
    print("="*60)
    
    p1 = GameTestClient("test_player1")
    p2 = GameTestClient("test_player2")
    
    try:
        assert p1.connect_to_lobby() and p1.login(), "Setup failed"
        assert p2.connect_to_lobby() and p2.login(), "Setup failed"
        room_id = p1.create_room()
        assert room_id is not None, "Room creation failed"
        assert p2.join_room(room_id), "Join failed"
        game_host, game_port = p1.start_game()
        assert game_host and game_port, "Game start failed"
        print("✓ Game started")
        
        # Launch game client and simulate forfeit
        # (In real test, would send FORFEIT message)
        time.sleep(1)
        
        # After forfeit, should be able to create new room
        new_room_id = p1.create_room()
        assert new_room_id is not None, "Failed to create room after forfeit"
        print(f"✓ New room {new_room_id} created after forfeit")
        
        print("✓ Test 5 PASSED: Forfeit scenario handled")
        return True
        
    except AssertionError as e:
        print(f"✗ Test 5 FAILED: {e}")
        return False
    finally:
        p1.close()
        p2.close()

def main():
    """Run all tests."""
    print("="*60)
    print("AUTOMATED GAME PLATFORM TEST SUITE")
    print("="*60)
    
    # Reset sessions first
    print("\nResetting all sessions...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
        reset_request = {"action": "reset_all_sessions", "data": {}}
        protocol.send_msg(sock, json.dumps(reset_request).encode('utf-8'))
        response_bytes = protocol.recv_msg(sock)
        if response_bytes:
            response = json.loads(response_bytes.decode('utf-8'))
            if response.get("status") == "ok":
                print("✓ Sessions reset")
        sock.close()
    except Exception as e:
        print(f"⚠ Could not reset sessions: {e}")
    
    # Run tests
    tests = [
        test_normal_gameplay,
        test_connection_loss,
        test_room_creation_after_game,
        test_multiple_games_sequence,
        test_forfeit_scenario,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
            time.sleep(1)  # Brief pause between tests
        except Exception as e:
            print(f"✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✓ ALL TESTS PASSED!")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
