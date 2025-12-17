# Database CRUD operations
# Clean interface for database operations

import sqlite3
import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseOperations:
    """Clean interface for database operations."""
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
    
    # User operations
    def create_user(self, username: str, password_hash: str, is_developer: bool = False) -> bool:
        """Create a new user."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, password_hash, is_developer)
                VALUES (?, ?, ?)
            """, (username, password_hash, 1 if is_developer else 0))
            self.conn.commit()
            logger.info(f"Created user: {username}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"User already exists: {username}")
            return False
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def update_user_status(self, username: str, status: str) -> bool:
        """Update user status."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users SET status = ? WHERE username = ?
            """, (status, username))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating user status: {e}")
            return False
    
    def set_developer_role(self, username: str, is_developer: bool) -> bool:
        """Set developer role for a user."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users SET is_developer = ? WHERE username = ?
            """, (1 if is_developer else 0, username))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error setting developer role: {e}")
            return False
    
    # Game operations
    def create_game(self, name: str, author: str, description: str = None, 
                   version: str = None) -> Optional[int]:
        """Create a new game. Returns game_id or None."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO games (name, author, description, current_version)
                VALUES (?, ?, ?, ?)
            """, (name, author, description, version))
            self.conn.commit()
            game_id = cursor.lastrowid
            logger.info(f"Created game: {name} (id: {game_id})")
            return game_id
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            return None
    
    def get_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get game by ID."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM games WHERE id = ?", (game_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting game: {e}")
            return None
    
    def get_games_by_author(self, author: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get all games by an author. Optionally include deleted games."""
        try:
            cursor = self.conn.cursor()
            if include_deleted:
                cursor.execute("SELECT * FROM games WHERE author = ? ORDER BY updated_at DESC", (author,))
            else:
                cursor.execute("SELECT * FROM games WHERE author = ? AND (deleted = 0 OR deleted IS NULL) ORDER BY updated_at DESC", (author,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting games by author: {e}")
            return []
    
    def list_all_games(self) -> List[Dict[str, Any]]:
        """List all games (excluding deleted ones)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM games WHERE (deleted = 0 OR deleted IS NULL) ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listing games: {e}")
            return []
    
    def search_games(self, query: str) -> List[Dict[str, Any]]:
        """Search games by name or author (excluding deleted ones)."""
        try:
            cursor = self.conn.cursor()
            search_term = f"%{query}%"
            cursor.execute("""
                SELECT * FROM games 
                WHERE (deleted = 0 OR deleted IS NULL)
                AND (name LIKE ? OR author LIKE ? OR description LIKE ?)
                ORDER BY updated_at DESC
            """, (search_term, search_term, search_term))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error searching games: {e}")
            return []
    
    def update_game(self, game_id: int, name: str = None, description: str = None,
                   current_version: str = None) -> bool:
        """Update game information."""
        try:
            cursor = self.conn.cursor()
            updates = []
            params = []
            
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if current_version is not None:
                updates.append("current_version = ?")
                params.append(current_version)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(game_id)
            
            query = f"UPDATE games SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating game: {e}")
            return False
    
    def delete_game(self, game_id: int) -> bool:
        """Soft delete a game (set deleted = 1). Keeps records for future features."""
        try:
            cursor = self.conn.cursor()
            # Soft delete: set deleted flag instead of actual deletion
            cursor.execute("UPDATE games SET deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (game_id,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting game: {e}")
            return False
    
    # Game version operations
    def create_game_version(self, game_id: int, version: str, file_path: str,
                           file_hash: str = None) -> Optional[int]:
        """Create a new game version. Returns version_id or None."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO game_versions (game_id, version, file_path, file_hash)
                VALUES (?, ?, ?, ?)
            """, (game_id, version, file_path, file_hash))
            self.conn.commit()
            version_id = cursor.lastrowid
            logger.info(f"Created game version: {version} for game {game_id}")
            return version_id
        except sqlite3.IntegrityError:
            logger.warning(f"Version {version} already exists for game {game_id}")
            return None
        except Exception as e:
            logger.error(f"Error creating game version: {e}")
            return None
    
    def get_game_version(self, game_id: int, version: str) -> Optional[Dict[str, Any]]:
        """Get a specific game version."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM game_versions 
                WHERE game_id = ? AND version = ?
            """, (game_id, version))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting game version: {e}")
            return None
    
    def get_latest_version(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get the latest version of a game."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM game_versions 
                WHERE game_id = ?
                ORDER BY uploaded_at DESC
                LIMIT 1
            """, (game_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
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
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO game_logs 
                (matchid, game_id, users, results, winner, reason, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                matchid,
                game_id,
                json.dumps(users) if users else "[]",
                json.dumps(results) if results else "[]",
                winner,
                reason,
                start_time,
                end_time
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Game log with matchid {matchid} already exists")
            return False
        except Exception as e:
            logger.error(f"Error creating game log: {e}")
            return False
    
    def get_game_logs(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get game logs, optionally filtered by user."""
        try:
            cursor = self.conn.cursor()
            if user_id:
                # Search in JSON array of users
                cursor.execute("""
                    SELECT * FROM game_logs 
                    WHERE users LIKE ?
                    ORDER BY start_time DESC
                """, (f'%"{user_id}"%',))
            else:
                cursor.execute("SELECT * FROM game_logs ORDER BY start_time DESC")
            
            logs = []
            for row in cursor.fetchall():
                log_dict = dict(row)
                # Parse JSON fields
                log_dict['users'] = json.loads(log_dict['users'])
                log_dict['results'] = json.loads(log_dict['results'])
                logs.append(log_dict)
            return logs
        except Exception as e:
            logger.error(f"Error getting game logs: {e}")
            return []

