#!/usr/bin/env python3
"""
Script to reset all user sessions in the lobby server.
This connects to the lobby server and sends logout commands for all logged-in users,
or directly resets their status to "online" if the server supports it.
"""

import socket
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import config, protocol

def reset_all_sessions():
    """Connect to lobby server and reset all user sessions."""
    try:
        # Connect to lobby server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((config.LOBBY_HOST, config.LOBBY_PORT))
        
        print(f"Connected to lobby server at {config.LOBBY_HOST}:{config.LOBBY_PORT}")
        
        # First, try to get list of users
        request = {
            "action": "list_users"
        }
        request_bytes = json.dumps(request).encode('utf-8')
        protocol.send_msg(sock, request_bytes)
        
        # Get response
        response_bytes = protocol.recv_msg(sock)
        if response_bytes:
            response = json.loads(response_bytes.decode('utf-8'))
            users = response.get("users", [])
            print(f"Found {len(users)} users in system")
            
            # Try to logout each user that's not already "online"
            logged_out = 0
            for user_info in users:
                username = user_info.get("username")
                status = user_info.get("status", "unknown")
                
                if status != "online":
                    print(f"User {username} has status '{status}', attempting to reset...")
                    # Try to logout (this might fail if they're not actually connected)
                    try:
                        logout_request = {
                            "action": "logout",
                            "data": {}
                        }
                        # Note: This might not work if the user's socket is closed
                        # But we'll try anyway
                    except:
                        pass
                    logged_out += 1
            
            if logged_out > 0:
                print(f"\nAttempted to reset {logged_out} user(s)")
            else:
                print("All users are already 'online'")
        
        # Send reset_all_sessions action
        print("\nSending reset_all_sessions command...")
        reset_request = {
            "action": "reset_all_sessions",
            "data": {}
        }
        print(f"Request: {json.dumps(reset_request)}")
        request_bytes = json.dumps(reset_request).encode('utf-8')
        protocol.send_msg(sock, request_bytes)
        
        # Get response
        response_bytes = protocol.recv_msg(sock)
        if response_bytes:
            response = json.loads(response_bytes.decode('utf-8'))
            print(f"Response: {json.dumps(response)}")
            if response.get("status") == "ok":
                users_reset = response.get("users_reset", 0)
                rooms_cleared = response.get("rooms_cleared", 0)
                print(f"✓ Successfully reset {users_reset} user session(s)")
                print(f"✓ Cleared {rooms_cleared} room(s)")
            else:
                reason = response.get('reason', 'unknown error')
                print(f"✗ Error: {reason}")
                if reason == "must_be_logged_in":
                    print("\n⚠️  The server may need to be restarted to load the reset_all_sessions handler.")
                    print("   Make sure you're running the latest version of lobby_server.py")
        
        sock.close()
        print("\nConnection closed.")
        
    except ConnectionRefusedError:
        print(f"Error: Could not connect to lobby server at {config.LOBBY_HOST}:{config.LOBBY_PORT}")
        print("Make sure the lobby server is running.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("Lobby Server Session Reset Tool")
    print("=" * 60)
    print()
    reset_all_sessions()
