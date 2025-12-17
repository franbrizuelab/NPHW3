#!/usr/bin/env python3
"""
Create test users for development/testing
Usage: python create_test_users.py
"""

import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from common.db_schema import initialize_database
from common.password_utils import hash_password

def main():
    db_ops = initialize_database()
    
    # Test users to create
    test_users = [
        {"username": "dev", "password": "dev123", "is_developer": True},
        {"username": "alice", "password": "alice123", "is_developer": True},
        {"username": "bob", "password": "bob123", "is_developer": False},
        {"username": "user", "password": "user123", "is_developer": False},
    ]
    
    print("Creating test users...")
    print()
    
    created = 0
    skipped = 0
    
    for user_info in test_users:
        username = user_info["username"]
        password = user_info["password"]
        is_dev = user_info["is_developer"]
        
        # Check if user already exists
        existing = db_ops.get_user(username)
        if existing:
            print(f"  ⚠ User '{username}' already exists (skipping)")
            skipped += 1
            continue
        
        # Create user
        password_hash = hash_password(password)
        if db_ops.create_user(username, password_hash, is_dev):
            dev_status = " (developer)" if is_dev else ""
            print(f"  ✓ Created user '{username}'{dev_status}")
            print(f"    Password: {password}")
            created += 1
        else:
            print(f"  ✗ Failed to create user '{username}'")
    
    print()
    print(f"Created {created} users, skipped {skipped} existing users")
    print()
    print("You can now login with:")
    for user_info in test_users:
        username = user_info["username"]
        password = user_info["password"]
        is_dev = " (developer)" if user_info["is_developer"] else ""
        print(f"  {username} / {password}{is_dev}")

if __name__ == "__main__":
    main()



