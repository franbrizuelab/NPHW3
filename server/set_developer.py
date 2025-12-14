#!/usr/bin/env python3
"""
Helper script to set a user as a developer
Usage: python set_developer.py <username>
"""

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common.db_schema import initialize_database
from common.db_operations import DatabaseOperations

def main():
    if len(sys.argv) < 2:
        print("Usage: python set_developer.py <username>")
        print("Example: python set_developer.py alice")
        sys.exit(1)
    
    username = sys.argv[1]
    
    try:
        conn = initialize_database()
        db_ops = DatabaseOperations(conn)
        
        # Check if user exists
        user = db_ops.get_user(username)
        if not user:
            print(f"Error: User '{username}' does not exist.")
            print("Please register the user first using the client.")
            sys.exit(1)
        
        # Set developer role
        if db_ops.set_developer_role(username, True):
            print(f"✓ User '{username}' is now a developer!")
        else:
            print(f"✗ Failed to set developer role for '{username}'")
            sys.exit(1)
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

