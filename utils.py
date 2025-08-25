"""
Utility functions for the Telegram View Booster Bot
"""
import re
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

class Utils:
    """Utility functions"""
    
    @staticmethod
    def is_valid_phone(phone: str) -> bool:
        """Validate phone number format"""
        # Remove all non-digits
        digits_only = re.sub(r'\D', '', phone)
        
        # Check if it's a valid length (7-15 digits)
        return 7 <= len(digits_only) <= 15
    
    @staticmethod
    def format_phone(phone: str) -> str:
        """Format phone number with + prefix"""
        digits_only = re.sub(r'\D', '', phone)
        if not digits_only.startswith('1') and len(digits_only) >= 10:
            return f"+{digits_only}"
        return f"+{digits_only}"
    
    @staticmethod
    def is_valid_telegram_link(link: str) -> bool:
        """Validate Telegram channel/group link"""
        patterns = [
            r'^https://t\.me/[a-zA-Z0-9_]{5,}$',  # Public channels
            r'^https://t\.me/joinchat/[a-zA-Z0-9_-]+$',  # Private invite links
            r'^@[a-zA-Z0-9_]{5,}$',  # Username format
            r'^[a-zA-Z0-9_]{5,}$',  # Just username without @
        ]
        
        return any(re.match(pattern, link.strip()) for pattern in patterns)
    
    @staticmethod
    def normalize_telegram_link(link: str) -> str:
        """Normalize Telegram link to standard format"""
        link = link.strip()
        
        # If it's just a username, add https://t.me/
        if re.match(r'^[a-zA-Z0-9_]{5,}$', link):
            return f"https://t.me/{link}"
        
        # If it starts with @, remove @ and add https://t.me/
        if link.startswith('@'):
            return f"https://t.me/{link[1:]}"
        
        # If it's already a full URL, return as is
        if link.startswith('https://t.me/'):
            return link
        
        return link
    
    @staticmethod
    def parse_user_settings(settings_json: str) -> Dict[str, Any]:
        """Parse user settings from JSON string"""
        try:
            if not settings_json:
                return {
                    "views_only": False,  # Default: views + read
                    "account_rotation": True,
                    "delay_level": "medium",
                    "auto_join": True
                }
            return json.loads(settings_json)
        except Exception as e:
            logger.error(f"Error parsing user settings: {e}")
            return {
                "views_only": False,
                "account_rotation": True, 
                "delay_level": "medium",
                "auto_join": True
            }
    
    @staticmethod
    def serialize_user_settings(settings: Dict[str, Any]) -> str:
        """Serialize user settings to JSON string"""
        try:
            return json.dumps(settings)
        except Exception as e:
            logger.error(f"Error serializing user settings: {e}")
            return "{}"
    
    @staticmethod
    def format_datetime(dt_str: Optional[str]) -> str:
        """Format datetime string for display"""
        if not dt_str:
            return "Never"
        
        try:
            dt = datetime.fromisoformat(dt_str)
            now = datetime.now()
            diff = now - dt
            
            if diff.days > 0:
                return f"{diff.days} days ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours} hours ago"
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f"{minutes} minutes ago"
            else:
                return "Just now"
        except Exception as e:
            logger.error(f"Error formatting datetime {dt_str}: {e}")
            return "Unknown"
    
    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format duration in seconds to human readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    @staticmethod
    def get_delay_range(delay_level: str) -> tuple:
        """Get delay range based on level"""
        delay_ranges = {
            "low": (1, 2),
            "medium": (2, 5),
            "high": (5, 10)
        }
        return delay_ranges.get(delay_level, (2, 5))
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 50) -> str:
        """Truncate text with ellipsis"""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
    
    @staticmethod
    def extract_message_ids(text: str) -> List[int]:
        """Extract message IDs from text input"""
        try:
            # Split by comma, space, or newline
            parts = re.split(r'[,\s\n]+', text.strip())
            message_ids = []
            
            for part in parts:
                if part.isdigit():
                    message_ids.append(int(part))
                elif '-' in part and all(p.isdigit() for p in part.split('-')):
                    # Handle ranges like "1-5"
                    start, end = map(int, part.split('-'))
                    message_ids.extend(range(start, end + 1))
            
            return list(set(message_ids))  # Remove duplicates
        except Exception as e:
            logger.error(f"Error extracting message IDs from '{text}': {e}")
            return []
    
    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to integer"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def escape_markdown(text: str) -> str:
        """Escape markdown special characters"""
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    @staticmethod
    async def retry_async(coro_func, max_attempts: int = 3, delay: float = 1.0):
        """Retry an async function with exponential backoff"""
        for attempt in range(max_attempts):
            try:
                return await coro_func()
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
    
    @staticmethod
    def format_account_status(account: Dict[str, Any]) -> str:
        """Format account status with emoji and description"""
        status = account.get("status", "unknown")
        phone = account.get("phone", "Unknown")
        
        status_info = {
            "active": ("✅", "Active"),
            "banned": ("🚫", "Banned"),
            "floodwait": ("⏳", "Flood Wait"),
            "inactive": ("❌", "Inactive")
        }
        
        emoji, description = status_info.get(status, ("❓", "Unknown"))
        
        # Add flood wait time if applicable
        if status == "floodwait" and account.get("flood_wait_until"):
            try:
                wait_until = datetime.fromisoformat(account["flood_wait_until"])
                if wait_until > datetime.now():
                    remaining = wait_until - datetime.now()
                    description += f" ({Utils.format_duration(int(remaining.total_seconds()))})"
                else:
                    description = "Ready"
                    emoji = "✅"
            except:
                pass
        
        return f"{emoji} {phone} - {description}"
    
    @staticmethod
    def validate_message_ids_input(text: str) -> tuple:
        """
        Validate message IDs input
        Returns (is_valid, message_ids, error_message)
        """
        if not text.strip():
            return False, [], "Please enter message IDs"
        
        message_ids = Utils.extract_message_ids(text)
        
        if not message_ids:
            return False, [], "No valid message IDs found. Use numbers separated by commas or spaces."
        
        if len(message_ids) > 100:
            return False, [], "Too many message IDs. Maximum 100 allowed."
        
        return True, message_ids, ""
