# Database schema definitions and initialization utilities
# JSON file storage initialization for the game platform

import logging
import os
import json

logger = logging.getLogger(__name__)

# Storage directory
STORAGE_DIR = 'storage'

def initialize_database(storage_dir: str = STORAGE_DIR):
    """
    Initialize the JSON file storage, creating empty JSON files if they don't exist.
    Returns a DatabaseOperations instance.
    """
    from common.db_operations import DatabaseOperations
    
    # Ensure storage directory exists
    os.makedirs(storage_dir, exist_ok=True)
    
    # Initialize DatabaseOperations (which will create empty JSON files if needed)
    db_ops = DatabaseOperations(storage_dir=storage_dir)
    
    # Ensure all JSON files exist with proper structure
    files_to_init = [
        (os.path.join(storage_dir, 'users.json'), 'users'),
        (os.path.join(storage_dir, 'games.json'), 'games'),
        (os.path.join(storage_dir, 'game_versions.json'), 'game_versions'),
        (os.path.join(storage_dir, 'game_logs.json'), 'game_logs'),
    ]
    
    for filepath, collection_name in files_to_init:
        if not os.path.exists(filepath):
            # Create empty file with proper structure
            default_data = {
                collection_name: [],
                "next_id": 1
            }
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, indent=2)
                logger.info(f"Created {filepath}")
            except Exception as e:
                logger.error(f"Failed to create {filepath}: {e}")
    
    logger.info("JSON storage initialized successfully")
    return db_ops
