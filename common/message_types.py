# Message type constants and validation
# Defines all message types used in the protocol

# Authentication actions
ACTION_REGISTER = "register"
ACTION_LOGIN = "login"
ACTION_LOGOUT = "logout"

# Room actions
ACTION_LIST_ROOMS = "list_rooms"
ACTION_LIST_USERS = "list_users"
ACTION_CREATE_ROOM = "create_room"
ACTION_JOIN_ROOM = "join_room"
ACTION_LEAVE_ROOM = "leave_room"
ACTION_START_GAME = "start_game"
ACTION_INVITE = "invite"
ACTION_GAME_OVER = "game_over"

# Game browsing actions (available to all)
ACTION_LIST_GAMES = "list_games"
ACTION_SEARCH_GAMES = "search_games"
ACTION_DOWNLOAD_GAME = "download_game"
ACTION_GET_GAME_INFO = "get_game_info"

# Developer actions (require is_developer=True)
ACTION_UPLOAD_GAME = "upload_game"
ACTION_UPDATE_GAME = "update_game"
ACTION_REMOVE_GAME = "remove_game"

# Query actions
ACTION_QUERY_GAMELOGS = "query_gamelogs"

# Message types (for responses)
MSG_TYPE_ROOM_UPDATE = "ROOM_UPDATE"
MSG_TYPE_KICKED_FROM_ROOM = "KICKED_FROM_ROOM"
MSG_TYPE_INVITE_RECEIVED = "INVITE_RECEIVED"
MSG_TYPE_GAME_START = "GAME_START"
MSG_TYPE_GAMELOG_RESPONSE = "gamelog_response"

# Game server message types
MSG_TYPE_WELCOME = "WELCOME"
MSG_TYPE_INPUT = "INPUT"
MSG_TYPE_FORFEIT = "FORFEIT"
MSG_TYPE_SNAPSHOT = "SNAPSHOT"
MSG_TYPE_GAME_OVER = "GAME_OVER"

def validate_request(request: dict) -> tuple[bool, str]:
    """
    Validate a request message structure.
    
    Args:
        request: Dictionary containing the request
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(request, dict):
        return False, "Request must be a dictionary"
    
    if 'action' not in request:
        return False, "Request must contain 'action' field"
    
    action = request.get('action')
    if not isinstance(action, str):
        return False, "Action must be a string"
    
    # Validate action-specific requirements
    if action in [ACTION_REGISTER, ACTION_LOGIN]:
        if 'data' not in request:
            return False, f"Action '{action}' requires 'data' field"
        data = request.get('data', {})
        if 'user' not in data and 'username' not in data:
            return False, f"Action '{action}' requires 'user' or 'username' in data"
        if 'pass' not in data and 'password' not in data:
            return False, f"Action '{action}' requires 'pass' or 'password' in data"
    
    if action == ACTION_UPLOAD_GAME:
        if 'data' not in request:
            return False, "Action 'upload_game' requires 'data' field"
        data = request.get('data', {})
        required_fields = ['name', 'version', 'file_data']
        for field in required_fields:
            if field not in data:
                return False, f"Action 'upload_game' requires '{field}' in data"
    
    if action == ACTION_UPDATE_GAME:
        if 'data' not in request:
            return False, "Action 'update_game' requires 'data' field"
        data = request.get('data', {})
        if 'game_id' not in data:
            return False, "Action 'update_game' requires 'game_id' in data"
        if 'version' not in data and 'file_data' not in data:
            return False, "Action 'update_game' requires at least 'version' or 'file_data' in data"
    
    if action == ACTION_REMOVE_GAME:
        if 'data' not in request:
            return False, "Action 'remove_game' requires 'data' field"
        data = request.get('data', {})
        if 'game_id' not in data:
            return False, "Action 'remove_game' requires 'game_id' in data"
    
    if action == ACTION_DOWNLOAD_GAME:
        if 'data' not in request:
            return False, "Action 'download_game' requires 'data' field"
        data = request.get('data', {})
        if 'game_id' not in data:
            return False, "Action 'download_game' requires 'game_id' in data"
    
    if action == ACTION_SEARCH_GAMES:
        if 'data' not in request:
            return False, "Action 'search_games' requires 'data' field"
        data = request.get('data', {})
        if 'query' not in data:
            return False, "Action 'search_games' requires 'query' in data"
    
    return True, ""

def is_developer_action(action: str) -> bool:
    """Check if an action requires developer privileges."""
    developer_actions = [
        ACTION_UPLOAD_GAME,
        ACTION_UPDATE_GAME,
        ACTION_REMOVE_GAME
    ]
    return action in developer_actions

