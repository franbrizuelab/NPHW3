# Database CRUD operations
# Clean interface for database operations

import json
import logging
import os
import threading
import tempfile
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseOperations:
    """Clean interface for database operations using JSON file storage."""
    
    def __init__(self, storage_dir: str = 'storage'):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
        # File paths
        self.users_file = os.path.join(storage_dir, 'users.json')
        self.games_file = os.path.join(storage_dir, 'games.json')
        self.game_versions_file = os.path.join(storage_dir, 'game_versions.json')
        self.game_logs_file = os.path.join(storage_dir, 'game_logs.json')
        
        # Thread locks for each file (one lock per JSON file)
        self.users_lock = threading.Lock()
        self.games_lock = threading.Lock()
        self.game_versions_lock = threading.Lock()
        self.game_logs_lock = threading.Lock()
    
    def _load_json_file(self, filepath: str, collection_name: str, lock: threading.Lock) -> Dict[str, Any]:
        """Load JSON file into memory with locking."""
        with lock:
            if not os.path.exists(filepath):
                # Return default structure
                return {collection_name: [], "next_id": 1}
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Ensure structure exists
                    if collection_name not in data:
                        data[collection_name] = []
                    if "next_id" not in data:
                        data["next_id"] = 1
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading {filepath}: {e}")
                # Return default structure on error
                return {collection_name: [], "next_id": 1}
    
    def _save_json_file(self, filepath: str, data: Dict[str, Any], lock: threading.Lock):
        """Save JSON file atomically (write to temp file, then rename)."""
        with lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(filepath) or self.storage_dir, exist_ok=True)
                # Write to temporary file first (in same directory for atomic rename to work)
                temp_dir = os.path.dirname(filepath) or self.storage_dir
                temp_fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix='.tmp')
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    # Atomic rename
                    os.replace(temp_path, filepath)
                except Exception as e:
                    # Clean up temp file on error
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                    raise e
            except Exception as e:
                logger.error(f"Error saving {filepath}: {e}")
                raise
    
    # User operations
    def create_user(self, username: str, password_hash: str, is_developer: bool = False) -> bool:
        """Create a new user."""
        try:
            data = self._load_json_file(self.users_file, "users", self.users_lock)
            
            # Check if user already exists
            for user in data["users"]:
                if user.get("username") == username:
                    logger.warning(f"User already exists: {username}")
                    return False
            
            # Create new user
            new_user = {
                "id": data["next_id"],
                "username": username,
                "password_hash": password_hash,
                "status": "offline",
                "is_developer": bool(is_developer),
                "created_at": datetime.now().isoformat()
            }
            
            data["users"].append(new_user)
            data["next_id"] += 1
            
            self._save_json_file(self.users_file, data, self.users_lock)
            logger.info(f"Created user: {username}")
            return True
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        try:
            data = self._load_json_file(self.users_file, "users", self.users_lock)
            for user in data["users"]:
                if user.get("username") == username:
                    # Convert boolean for compatibility
                    user_copy = user.copy()
                    user_copy["is_developer"] = bool(user_copy.get("is_developer", False))
                    return user_copy
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def update_user_status(self, username: str, status: str) -> bool:
        """Update user status."""
        try:
            data = self._load_json_file(self.users_file, "users", self.users_lock)
            for user in data["users"]:
                if user.get("username") == username:
                    user["status"] = status
                    self._save_json_file(self.users_file, data, self.users_lock)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating user status: {e}")
            return False
    
    def set_developer_role(self, username: str, is_developer: bool) -> bool:
        """Set developer role for a user."""
        try:
            data = self._load_json_file(self.users_file, "users", self.users_lock)
            for user in data["users"]:
                if user.get("username") == username:
                    user["is_developer"] = bool(is_developer)
                    self._save_json_file(self.users_file, data, self.users_lock)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error setting developer role: {e}")
            return False
    
    # Game operations
    def create_game(self, name: str, author: str, description: str = None, 
                   version: str = None) -> Optional[int]:
        """Create a new game. Returns game_id or None."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            
            new_game = {
                "id": data["next_id"],
                "name": name,
                "author": author,
                "description": description,
                "current_version": version,
                "deleted": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            game_id = data["next_id"]
            data["games"].append(new_game)
            data["next_id"] += 1
            
            self._save_json_file(self.games_file, data, self.games_lock)
            logger.info(f"Created game: {name} (id: {game_id})")
            return game_id
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            return None
    
    def get_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get game by ID."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            for game in data["games"]:
                if game.get("id") == game_id:
                    game_copy = game.copy()
                    game_copy["deleted"] = bool(game_copy.get("deleted", False))
                    return game_copy
            return None
        except Exception as e:
            logger.error(f"Error getting game: {e}")
            return None
    
    def get_games_by_author(self, author: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get all games by an author. Optionally include deleted games."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            games = []
            for game in data["games"]:
                if game.get("author") == author:
                    if include_deleted or not game.get("deleted", False):
                        game_copy = game.copy()
                        game_copy["deleted"] = bool(game_copy.get("deleted", False))
                        games.append(game_copy)
            
            # Sort by updated_at descending
            games.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return games
        except Exception as e:
            logger.error(f"Error getting games by author: {e}")
            return []
    
    def list_all_games(self) -> List[Dict[str, Any]]:
        """List all games (excluding deleted ones)."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            games = []
            for game in data["games"]:
                if not game.get("deleted", False):
                    game_copy = game.copy()
                    game_copy["deleted"] = bool(game_copy.get("deleted", False))
                    games.append(game_copy)
            
            # Sort by updated_at descending
            games.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return games
        except Exception as e:
            logger.error(f"Error listing games: {e}")
            return []
    
    def search_games(self, query: str) -> List[Dict[str, Any]]:
        """Search games by name or author (excluding deleted ones)."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            query_lower = query.lower()
            games = []
            for game in data["games"]:
                if not game.get("deleted", False):
                    # Search in name, author, and description
                    name = str(game.get("name", "")).lower()
                    author = str(game.get("author", "")).lower()
                    description = str(game.get("description", "")).lower()
                    if query_lower in name or query_lower in author or query_lower in description:
                        game_copy = game.copy()
                        game_copy["deleted"] = bool(game_copy.get("deleted", False))
                        games.append(game_copy)
            
            # Sort by updated_at descending
            games.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return games
        except Exception as e:
            logger.error(f"Error searching games: {e}")
            return []
    
    def update_game(self, game_id: int, name: str = None, description: str = None,
                   current_version: str = None) -> bool:
        """Update game information."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            for game in data["games"]:
                if game.get("id") == game_id:
                    if name is not None:
                        game["name"] = name
                    if description is not None:
                        game["description"] = description
                    if current_version is not None:
                        game["current_version"] = current_version
                    game["updated_at"] = datetime.now().isoformat()
                    self._save_json_file(self.games_file, data, self.games_lock)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating game: {e}")
            return False
    
    def delete_game(self, game_id: int) -> bool:
        """Soft delete a game (set deleted = True). Keeps records for future features."""
        try:
            data = self._load_json_file(self.games_file, "games", self.games_lock)
            for game in data["games"]:
                if game.get("id") == game_id:
                    game["deleted"] = True
                    game["updated_at"] = datetime.now().isoformat()
                    self._save_json_file(self.games_file, data, self.games_lock)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error deleting game: {e}")
            return False
    
    # Game version operations
    def create_game_version(self, game_id: int, version: str, file_path: str,
                           file_hash: str = None) -> Optional[int]:
        """Create a new game version. Returns version_id or None."""
        try:
            data = self._load_json_file(self.game_versions_file, "game_versions", self.game_versions_lock)
            
            # Check if version already exists
            for v in data["game_versions"]:
                if v.get("game_id") == game_id and v.get("version") == version:
                    logger.warning(f"Version {version} already exists for game {game_id}")
                    return None
            
            new_version = {
                "id": data["next_id"],
                "game_id": game_id,
                "version": version,
                "file_path": file_path,
                "file_hash": file_hash,
                "uploaded_at": datetime.now().isoformat()
            }
            
            version_id = data["next_id"]
            data["game_versions"].append(new_version)
            data["next_id"] += 1
            
            self._save_json_file(self.game_versions_file, data, self.game_versions_lock)
            logger.info(f"Created game version: {version} for game {game_id}")
            return version_id
        except Exception as e:
            logger.error(f"Error creating game version: {e}")
            return None
    
    def get_game_version(self, game_id: int, version: str) -> Optional[Dict[str, Any]]:
        """Get a specific game version."""
        try:
            data = self._load_json_file(self.game_versions_file, "game_versions", self.game_versions_lock)
            for v in data["game_versions"]:
                if v.get("game_id") == game_id and v.get("version") == version:
                    return v.copy()
            return None
        except Exception as e:
            logger.error(f"Error getting game version: {e}")
            return None
    
    def get_latest_version(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get the latest version of a game."""
        try:
            data = self._load_json_file(self.game_versions_file, "game_versions", self.game_versions_lock)
            versions = [v for v in data["game_versions"] if v.get("game_id") == game_id]
            if versions:
                # Sort by uploaded_at descending and return the first
                versions.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
                return versions[0].copy()
            return None
        except Exception as e:
            logger.error(f"Error getting latest version: {e}")
            return None
    
    # Game log operations
    def create_game_log(self, matchid: str, game_id: int = None, users: List[str] = None,
                       results: List[Dict] = None, winner: str = None, reason: str = None,
                       start_time: str = None, end_time: str = None) -> bool:
        """Create a game log entry."""
        try:
            data = self._load_json_file(self.game_logs_file, "game_logs", self.game_logs_lock)
            
            # Check if matchid already exists
            for log in data["game_logs"]:
                if log.get("matchid") == matchid:
                    logger.warning(f"Game log with matchid {matchid} already exists")
                    return False
            
            new_log = {
                "id": data["next_id"],
                "matchid": matchid,
                "game_id": game_id,
                "users": users if users else [],
                "results": results if results else [],
                "winner": winner,
                "reason": reason,
                "start_time": start_time,
                "end_time": end_time
            }
            
            data["game_logs"].append(new_log)
            data["next_id"] += 1
            
            self._save_json_file(self.game_logs_file, data, self.game_logs_lock)
            return True
        except Exception as e:
            logger.error(f"Error creating game log: {e}")
            return False
    
    def get_game_logs(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get game logs, optionally filtered by user."""
        try:
            data = self._load_json_file(self.game_logs_file, "game_logs", self.game_logs_lock)
            logs = []
            for log in data["game_logs"]:
                if user_id:
                    # Check if user_id is in the users list
                    users = log.get("users", [])
                    if user_id in users:
                        log_copy = log.copy()
                        # Ensure users and results are lists (they should already be)
                        log_copy["users"] = list(log_copy.get("users", []))
                        log_copy["results"] = list(log_copy.get("results", []))
                        logs.append(log_copy)
                else:
                    log_copy = log.copy()
                    log_copy["users"] = list(log_copy.get("users", []))
                    log_copy["results"] = list(log_copy.get("results", []))
                    logs.append(log_copy)
            
            # Sort by start_time descending
            logs.sort(key=lambda x: x.get("start_time", "") or "", reverse=True)
            return logs
        except Exception as e:
            logger.error(f"Error getting game logs: {e}")
            return []
