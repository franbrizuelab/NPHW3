"""
Game Store Screen
Handles game browsing, game details, and rating submission
"""

import pygame
import sys
import os

# Add project root to path BEFORE any other imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from common import config
from client.shared import send_to_lobby_queue
from client.client_gui import CONFIG, Button, draw_text

# Store screen state
store_state = {
    "view": "browse",  # "browse", "detail", "rate"
    "games": [],
    "selected_game": None,
    "selected_game_ratings": [],
    "average_rating": None,
    "user_rating": None,
    "rating_eligible": False,
    "has_rated": False,
    "rating_input": {
        "rating": 0,  # 0 means not set, 1-5 for star rating
        "comment": "",
        "comment_active": False
    },
    "error_message": "",
    "success_message": ""
}


def draw_text_wrapped(surface, text, x, y, max_width, font, color, line_spacing=5):
    """Draw text with word wrapping."""
    words = text.split(' ')
    lines = []
    current_line = []
    current_width = 0
    
    for word in words:
        word_surface = font.render(word + ' ', True, color)
        word_width = word_surface.get_width()
        
        if current_width + word_width <= max_width:
            current_line.append(word)
            current_width += word_width
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_width = word_width
    
    if current_line:
        lines.append(' '.join(current_line))
    
    y_offset = y
    for line in lines:
        draw_text(surface, line, x, y_offset, font, color)
        y_offset += font.get_height() + line_spacing
    
    return y_offset - y  # Return total height


def fetch_games():
    """Fetch game list from server."""
    send_to_lobby_queue({
        "action": "list_games"
    })


def fetch_game_details(game_id):
    """Fetch game details and ratings."""
    send_to_lobby_queue({
        "action": "get_game_info",
        "data": {"game_id": game_id}
    })
    send_to_lobby_queue({
        "action": "get_game_ratings",
        "data": {"game_id": game_id, "limit": 5}
    })
    send_to_lobby_queue({
        "action": "check_rating_eligibility",
        "data": {"game_id": game_id}
    })


def fetch_user_rating(game_id, username):
    """Fetch user's rating for a game."""
    send_to_lobby_queue({
        "action": "get_user_rating",
        "data": {"game_id": game_id}
    })


def submit_rating(game_id, rating, comment, username):
    """Submit a rating to the server."""
    send_to_lobby_queue({
        "action": "submit_rating",
        "data": {
            "game_id": game_id,
            "rating": rating,
            "comment": comment
        }
    })


def draw_star_rating(surface, x, y, rating, max_rating=5, star_size=15, font=None):
    """Draw star rating display."""
    if font is None:
        font = pygame.font.Font(CONFIG["FONTS"]["DEFAULT_FONT"], CONFIG["FONTS"]["SIZES"]["TINY"])
    
    # Draw stars
    for i in range(max_rating):
        star_x = x + i * (star_size + 3)
        if i < rating:
            color = (255, 215, 0)  # Gold for filled stars
            star_char = "★"
        else:
            color = (100, 100, 100)  # Gray for empty stars
            star_char = "☆"
        
        star_surface = font.render(star_char, True, color)
        surface.blit(star_surface, (star_x, y))
    
    # Draw numeric rating
    if rating > 0:
        rating_text = f"{rating:.1f}" if isinstance(rating, float) else str(rating)
        text_surface = font.render(rating_text, True, CONFIG["COLORS"]["TEXT"])
        surface.blit(text_surface, (x + max_rating * (star_size + 3) + 10, y))


def draw_browse_screen(screen, fonts):
    """Draw the game browsing screen."""
    draw_text(screen, "Game Store", 50, 20, fonts["LARGE"], CONFIG["COLORS"]["TEXT"])
    draw_text(screen, "Esc to exit", CONFIG["SCREEN"]["WIDTH"] - 120, 20, fonts["TINY"], CONFIG["COLORS"]["TEXT"])
    
    if not store_state["games"]:
        draw_text(screen, "No games available", 50, 100, fonts["MEDIUM"], CONFIG["COLORS"]["TEXT"])
        return
    
    # Draw games list
    y_offset = 80
    game_buttons = []
    
    for i, game in enumerate(store_state["games"]):
        # Game button
        game_name = game.get("name", "Unknown")
        author = game.get("author", "Unknown")
        game_text = f"{i+1}. {game_name} by {author}"
        
        # Truncate if too long
        if len(game_text) > 50:
            game_text = game_text[:47] + "..."
        
        btn = Button(50, y_offset, 800, 35, fonts["SMALL"], game_text)
        btn.game_id = game.get("id")
        btn.game = game
        btn.draw(screen)
        game_buttons.append(btn)
        
        y_offset += 45
    
    store_state["game_buttons"] = game_buttons


def draw_detail_screen(screen, fonts):
    """Draw the game detail screen with ratings."""
    if not store_state["selected_game"]:
        store_state["view"] = "browse"
        return
    
    game = store_state["selected_game"]
    colors = CONFIG["COLORS"]
    
    # Header
    draw_text(screen, "Game Details", 50, 20, fonts["LARGE"], colors["TEXT"])
    draw_text(screen, "Esc: Back | R: Rate", CONFIG["SCREEN"]["WIDTH"] - 200, 20, fonts["TINY"], colors["TEXT"])
    
    y = 70
    
    # Game info
    draw_text(screen, f"Name: {game.get('name', 'Unknown')}", 50, y, fonts["MEDIUM"], colors["TEXT"])
    y += 35
    draw_text(screen, f"Author: {game.get('author', 'Unknown')}", 50, y, fonts["SMALL"], colors["TEXT"])
    y += 30
    draw_text(screen, f"Version: {game.get('current_version', 'N/A')}", 50, y, fonts["SMALL"], colors["TEXT"])
    y += 35
    
    # Description
    description = game.get('description', 'No description available.')
    draw_text(screen, "Description:", 50, y, fonts["SMALL"], colors["TEXT"])
    y += 25
    desc_height = draw_text_wrapped(screen, description, 50, y, 800, fonts["TINY"], colors["TEXT"], line_spacing=3)
    y += desc_height + 20
    
    # Average rating
    if store_state["average_rating"] is not None:
        draw_text(screen, "Average Rating:", 50, y, fonts["SMALL"], colors["TEXT"])
        draw_star_rating(screen, 200, y, store_state["average_rating"], font=fonts["TINY"])
        rating_count = len(store_state["selected_game_ratings"])
        draw_text(screen, f"({rating_count} review{'s' if rating_count != 1 else ''})", 300, y, fonts["TINY"], colors["TEXT"])
        y += 30
    else:
        draw_text(screen, "No ratings yet", 50, y, fonts["SMALL"], (150, 150, 150))
        y += 30
    
    # User's rating status
    if store_state["has_rated"] and store_state["user_rating"]:
        user_rating = store_state["user_rating"]
        draw_text(screen, "Your Rating:", 50, y, fonts["SMALL"], colors["TEXT"])
        draw_star_rating(screen, 200, y, user_rating.get("rating", 0), font=fonts["TINY"])
        y += 30
    elif store_state["rating_eligible"]:
        draw_text(screen, "You can rate this game (Press R)", 50, y, fonts["TINY"], (150, 255, 150))
        y += 25
    else:
        draw_text(screen, "Play the game first to rate it", 50, y, fonts["TINY"], (150, 150, 150))
        y += 25
    
    # Recent reviews
    if store_state["selected_game_ratings"]:
        y += 10
        draw_text(screen, "Recent Reviews:", 50, y, fonts["SMALL"], colors["TEXT"])
        y += 30
        
        # Draw reviews (limit to 3-4 visible)
        for i, rating in enumerate(store_state["selected_game_ratings"][:4]):
            if y > CONFIG["SCREEN"]["HEIGHT"] - 100:
                break
            
            # Reviewer name and stars
            reviewer = rating.get("username", "Unknown")
            rating_val = rating.get("rating", 0)
            draw_text(screen, reviewer, 50, y, fonts["TINY"], colors["TEXT"])
            draw_star_rating(screen, 150, y, rating_val, font=fonts["TINY"])
            y += 20
            
            # Comment
            comment = rating.get("comment", "")
            if comment:
                comment_height = draw_text_wrapped(screen, comment, 70, y, 750, fonts["TINY"], (200, 200, 200), line_spacing=2)
                y += comment_height + 10
            else:
                y += 5
            
            pygame.draw.line(screen, (50, 50, 50), (50, y), (CONFIG["SCREEN"]["WIDTH"] - 50, y), 1)
            y += 15
    
    # Error/success messages
    if store_state["error_message"]:
        draw_text(screen, store_state["error_message"], 50, CONFIG["SCREEN"]["HEIGHT"] - 50, fonts["TINY"], colors["ERROR"])
    elif store_state["success_message"]:
        draw_text(screen, store_state["success_message"], 50, CONFIG["SCREEN"]["HEIGHT"] - 50, fonts["TINY"], (150, 255, 150))


def draw_rate_screen(screen, fonts):
    """Draw the rating submission screen."""
    if not store_state["selected_game"]:
        store_state["view"] = "detail"
        return
    
    game = store_state["selected_game"]
    colors = CONFIG["COLORS"]
    
    # Header
    draw_text(screen, f"Rate: {game.get('name', 'Unknown')}", 50, 20, fonts["MEDIUM"], colors["TEXT"])
    draw_text(screen, "Esc: Cancel | Enter: Submit", CONFIG["SCREEN"]["WIDTH"] - 220, 20, fonts["TINY"], colors["TEXT"])
    
    y = 100
    
    # Star rating selector
    draw_text(screen, "Rating (1-5 stars):", 50, y, fonts["SMALL"], colors["TEXT"])
    y += 30
    
    # Draw clickable stars
    star_x = 50
    star_size = 25
    mouse_pos = pygame.mouse.get_pos()
    
    for i in range(5):
        star_rect = pygame.Rect(star_x + i * (star_size + 5), y, star_size, star_size)
        hover = star_rect.collidepoint(mouse_pos)
        
        if i < store_state["rating_input"]["rating"]:
            color = (255, 215, 0)  # Gold
            star_char = "★"
        else:
            color = (100, 100, 100) if not hover else (150, 150, 150)
            star_char = "☆"
        
        star_font = pygame.font.Font(CONFIG["FONTS"]["DEFAULT_FONT"], star_size)
        star_surface = star_font.render(star_char, True, color)
        screen.blit(star_surface, (star_x + i * (star_size + 5), y))
    
    y += 50
    
    # Comment input
    draw_text(screen, "Comment (optional, max 500 chars):", 50, y, fonts["SMALL"], colors["TEXT"])
    y += 30
    
    # Comment box
    comment_box_rect = pygame.Rect(50, y, 800, 150)
    comment_color = CONFIG["COLORS"]["INPUT_ACTIVE"] if store_state["rating_input"]["comment_active"] else CONFIG["COLORS"]["INPUT_BOX"]
    pygame.draw.rect(screen, comment_color, comment_box_rect, 0)
    pygame.draw.rect(screen, CONFIG["COLORS"]["TEXT"], comment_box_rect, 2)
    
    # Draw comment text with wrapping
    comment = store_state["rating_input"]["comment"]
    if comment or store_state["rating_input"]["comment_active"]:
        draw_text_wrapped(screen, comment, 55, y + 5, 790, fonts["TINY"], CONFIG["COLORS"]["INPUT_TEXT"], line_spacing=3)
    else:
        draw_text(screen, "Enter your comment here...", 55, y + 5, fonts["TINY"], (100, 100, 100))
    
    # Character count
    char_count = len(comment)
    char_count_text = f"{char_count}/500"
    count_color = colors["ERROR"] if char_count > 500 else colors["TEXT"]
    draw_text(screen, char_count_text, 830, y + 130, fonts["TINY"], count_color)
    
    y += 170
    
    # Error message
    if store_state["error_message"]:
        draw_text(screen, store_state["error_message"], 50, y, fonts["TINY"], colors["ERROR"])
        y += 25
    
    # Submit button hint
    if store_state["rating_input"]["rating"] > 0:
        draw_text(screen, "Press Enter to submit rating", 50, y, fonts["TINY"], (150, 255, 150))
    else:
        draw_text(screen, "Please select a rating (1-5 stars)", 50, y, fonts["TINY"], colors["ERROR"])


def draw_store_screen(screen, fonts):
    """Main draw function for store screen."""
    if store_state["view"] == "browse":
        draw_browse_screen(screen, fonts)
    elif store_state["view"] == "detail":
        draw_detail_screen(screen, fonts)
    elif store_state["view"] == "rate":
        draw_rate_screen(screen, fonts)


def handle_store_events(event, g_state_lock, g_client_state, username):
    """Handle events for store screen."""
    global store_state
    
    # ESC key handling
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            if store_state["view"] == "browse":
                with g_state_lock:
                    g_client_state = "LOBBY"
            elif store_state["view"] == "detail":
                store_state["view"] = "browse"
                store_state["selected_game"] = None
                store_state["selected_game_ratings"] = []
                store_state["error_message"] = ""
                store_state["success_message"] = ""
            elif store_state["view"] == "rate":
                store_state["view"] = "detail"
                store_state["rating_input"]["rating"] = 0
                store_state["rating_input"]["comment"] = ""
                store_state["rating_input"]["comment_active"] = False
                store_state["error_message"] = ""
        
        # R key to rate (from detail screen)
        elif event.key == pygame.K_r and store_state["view"] == "detail":
            if store_state["rating_eligible"]:
                store_state["view"] = "rate"
                # Pre-fill if user already rated
                if store_state["user_rating"]:
                    store_state["rating_input"]["rating"] = store_state["user_rating"].get("rating", 0)
                    store_state["rating_input"]["comment"] = store_state["user_rating"].get("comment", "")
        
        # Enter to submit rating
        elif event.key == pygame.K_RETURN and store_state["view"] == "rate":
            rating = store_state["rating_input"]["rating"]
            if rating > 0:
                comment = store_state["rating_input"]["comment"][:500]  # Enforce max length
                game_id = store_state["selected_game"].get("id")
                submit_rating(game_id, rating, comment, username)
                # Clear input
                store_state["rating_input"]["rating"] = 0
                store_state["rating_input"]["comment"] = ""
                store_state["rating_input"]["comment_active"] = False
                store_state["error_message"] = ""
                store_state["success_message"] = "Rating submitted! Refreshing..."
                # Refresh after a short delay
                pygame.time.wait(500)
                if game_id:
                    fetch_game_details(game_id)
                    fetch_user_rating(game_id, username)
            else:
                store_state["error_message"] = "Please select a rating (1-5 stars)"
        
        # Comment input
        elif store_state["view"] == "rate" and store_state["rating_input"]["comment_active"]:
            if event.key == pygame.K_BACKSPACE:
                store_state["rating_input"]["comment"] = store_state["rating_input"]["comment"][:-1]
            elif event.unicode and len(store_state["rating_input"]["comment"]) < 500:
                store_state["rating_input"]["comment"] += event.unicode
    
    # Mouse clicks
    elif event.type == pygame.MOUSEBUTTONDOWN:
        if store_state["view"] == "browse":
            # Click on game button
            if "game_buttons" in store_state:
                for btn in store_state["game_buttons"]:
                    if btn.handle_event(event):
                        store_state["selected_game"] = btn.game
                        store_state["view"] = "detail"
                        store_state["error_message"] = ""
                        store_state["success_message"] = ""
                        fetch_game_details(btn.game_id)
                        fetch_user_rating(btn.game_id, username)
                        break
        
        elif store_state["view"] == "rate":
            # Click on comment box
            comment_box_rect = pygame.Rect(50, 200, 800, 150)
            if comment_box_rect.collidepoint(event.pos):
                store_state["rating_input"]["comment_active"] = True
            else:
                store_state["rating_input"]["comment_active"] = False
            
            # Click on stars
            star_x = 50
            star_size = 25
            y = 130
            for i in range(5):
                star_rect = pygame.Rect(star_x + i * (star_size + 5), y, star_size, star_size)
                if star_rect.collidepoint(event.pos):
                    store_state["rating_input"]["rating"] = i + 1
                    store_state["error_message"] = ""
                    break
    
    return g_client_state


def on_enter():
    """Called when entering the store screen."""
    store_state["view"] = "browse"
    store_state["selected_game"] = None
    store_state["selected_game_ratings"] = []
    store_state["average_rating"] = None
    store_state["user_rating"] = None
    store_state["rating_eligible"] = False
    store_state["has_rated"] = False
    store_state["error_message"] = ""
    store_state["success_message"] = ""
    fetch_games()


def process_server_response(msg, username):
    """Process responses from the server."""
    global store_state
    
    # Game list response
    if msg.get("status") == "ok" and "games" in msg:
        store_state["games"] = msg["games"]
    
    # Game info response
    if msg.get("status") == "ok" and "game" in msg:
        store_state["selected_game"] = msg["game"]
    
    # Ratings response
    if msg.get("status") == "ok" and "ratings" in msg:
        store_state["selected_game_ratings"] = msg.get("ratings", [])
        store_state["average_rating"] = msg.get("average_rating")
    
    # User rating response
    if msg.get("status") == "ok" and "rating" in msg:
        store_state["user_rating"] = msg["rating"]
        store_state["has_rated"] = msg["rating"] is not None
    
    # Eligibility response
    if msg.get("status") == "ok" and "eligible" in msg:
        store_state["rating_eligible"] = msg.get("eligible", False)
        store_state["has_rated"] = msg.get("has_rated", False)
    
    # Rating submission response
    if msg.get("status") == "ok" and msg.get("reason") == "rating_submitted":
        store_state["success_message"] = "Rating submitted successfully!"
        store_state["error_message"] = ""
        store_state["view"] = "detail"  # Return to detail view
        # Refresh ratings
        if store_state["selected_game"]:
            game_id = store_state["selected_game"].get("id")
            fetch_game_details(game_id)
            fetch_user_rating(game_id, username)
    
    # Error responses
    if msg.get("status") == "error":
        reason = msg.get("reason", "unknown_error")
        if reason == "user_has_not_played_game":
            store_state["error_message"] = "You must play the game before rating it"
        elif reason == "invalid_rating_range":
            store_state["error_message"] = "Rating must be between 1 and 5"
        elif reason == "comment_too_long":
            store_state["error_message"] = "Comment must be 500 characters or less"
        else:
            store_state["error_message"] = f"Error: {reason}"
        store_state["success_message"] = ""
