# Password hashing and verification utilities
# Uses bcrypt for secure password hashing

import bcrypt
import logging

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plaintext password to hash
        
    Returns:
        Hashed password as a string (bcrypt hash)
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a stored hash.
    
    Args:
        password: Plaintext password to verify
        password_hash: Stored password hash
        
    Returns:
        True if password matches, False otherwise
    """
    if not password or not password_hash:
        return False
    
    try:
        # bcrypt.checkpw returns True if password matches
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

