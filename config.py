"""
Configuration management using environment variables
"""
import os
from typing import List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for bot settings"""
    
    def __init__(self):
        # Telegram Bot Configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required in .env file")
        
        # Telegram API Configuration
        self.API_ID = os.getenv("API_ID")
        self.API_HASH = os.getenv("API_HASH")
        if not self.API_ID or not self.API_HASH:
            raise ValueError("API_ID and API_HASH are required in .env file")
        
        try:
            self.API_ID = int(self.API_ID)
        except ValueError:
            raise ValueError("API_ID must be a valid integer")
        
        # Admin Configuration
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS: List[int] = []
        if admin_ids_str:
            try:
                self.ADMIN_IDS = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]
            except ValueError:
                raise ValueError("ADMIN_IDS must be comma-separated integers")
        
        if not self.ADMIN_IDS:
            raise ValueError("At least one ADMIN_ID is required in .env file")
        
        # Database Configuration
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_data.db")
        
        # Bot Configuration
        self.DEFAULT_DELAY_MIN = int(os.getenv("DEFAULT_DELAY_MIN", "1"))
        self.DEFAULT_DELAY_MAX = int(os.getenv("DEFAULT_DELAY_MAX", "5"))
        self.MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
        self.SESSION_DIR = os.getenv("SESSION_DIR", "sessions")
        
        # Create session directory if it doesn't exist
        os.makedirs(self.SESSION_DIR, exist_ok=True)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.ADMIN_IDS
