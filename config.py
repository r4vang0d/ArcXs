"""
Configuration management using environment variables
"""
import os
import logging
from typing import List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables (optional for .env file)
load_dotenv('.env', verbose=True)

class Config:
    """Configuration class for bot settings"""
    
    def __init__(self):
        # Telegram Bot Configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required in environment variables")
        
        # Default Telegram API Configuration (fallback)
        self.DEFAULT_API_ID = int(os.getenv("DEFAULT_API_ID", "94575"))
        self.DEFAULT_API_HASH = os.getenv("DEFAULT_API_HASH", "a3406de8d171bb422bb6ddf3bbd800e2")
        
        # Legacy API Configuration (for backward compatibility)
        self.API_ID = os.getenv("API_ID", str(self.DEFAULT_API_ID))
        self.API_HASH = os.getenv("API_HASH", self.DEFAULT_API_HASH)
        
        try:
            self.API_ID = int(self.API_ID)
        except (ValueError, TypeError):
            logger.warning(f"Invalid API_ID format, using default: {self.DEFAULT_API_ID}")
            self.API_ID = self.DEFAULT_API_ID
        
        # Admin Configuration
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS: List[int] = []
        if admin_ids_str:
            try:
                self.ADMIN_IDS = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]
            except ValueError:
                raise ValueError("ADMIN_IDS must be comma-separated integers")
        
        if not self.ADMIN_IDS:
            raise ValueError("At least one ADMIN_ID is required in environment variables")
        
        # Database Configuration
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_data.db")
        
        # Bot Configuration
        try:
            self.DEFAULT_DELAY_MIN = int(os.getenv("DEFAULT_DELAY_MIN", "1"))
            self.DEFAULT_DELAY_MAX = int(os.getenv("DEFAULT_DELAY_MAX", "5"))
            self.MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
        except (ValueError, TypeError):
            self.DEFAULT_DELAY_MIN = 1
            self.DEFAULT_DELAY_MAX = 5
            self.MAX_RETRY_ATTEMPTS = 3
        self.SESSION_DIR = os.getenv("SESSION_DIR", "sessions")
        
        # Create session directory if it doesn't exist
        os.makedirs(self.SESSION_DIR, exist_ok=True)
        
        # ===== MASSIVE SCALE OPTIMIZATION SETTINGS =====
        # PostgreSQL Database for massive scale
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        
        # Performance settings for 2000+ accounts
        self.MAX_ACTIVE_CLIENTS = int(os.getenv('MAX_ACTIVE_CLIENTS', '100'))
        self.DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '20'))
        self.DB_MAX_POOL_SIZE = int(os.getenv('DB_MAX_POOL_SIZE', '50'))
        
        # Rate limiting settings (per account)
        self.CALLS_PER_MINUTE_PER_ACCOUNT = int(os.getenv('CALLS_PER_MINUTE_PER_ACCOUNT', '30'))
        self.CALLS_PER_HOUR_PER_ACCOUNT = int(os.getenv('CALLS_PER_HOUR_PER_ACCOUNT', '1000'))
        
        # Global rate limiting
        self.GLOBAL_CALLS_PER_MINUTE = int(os.getenv('GLOBAL_CALLS_PER_MINUTE', '150'))
        self.GLOBAL_CALLS_PER_HOUR = int(os.getenv('GLOBAL_CALLS_PER_HOUR', '5000'))
        
        # Batch processing settings
        self.BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))
        self.MAX_ACCOUNTS_PER_OPERATION = int(os.getenv('MAX_ACCOUNTS_PER_OPERATION', '100'))
        
        # Resource management
        self.CLIENT_CLEANUP_INTERVAL = int(os.getenv('CLIENT_CLEANUP_INTERVAL', '300'))  # 5 minutes
        self.CLIENT_MAX_IDLE_TIME = int(os.getenv('CLIENT_MAX_IDLE_TIME', '600'))  # 10 minutes
        self.LOG_CLEANUP_DAYS = int(os.getenv('LOG_CLEANUP_DAYS', '30'))
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.ADMIN_IDS
