#!/usr/bin/env python3
"""
Main entry point for the Telegram View Booster Bot
Combines Aiogram and Telethon for comprehensive channel management
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# Add current directory to Python path for imports
sys.path.append(str(Path(__file__).parent))

from telegram_bot import ViewBoosterBot
from config import Config
from database import DatabaseManager

# Configure logging with Windows Unicode support
import platform

# Create handlers with proper encoding
log_handlers = []

# File handler with UTF-8 encoding
log_handlers.append(logging.FileHandler('bot.log', encoding='utf-8'))

# Console handler with proper encoding for Windows
if platform.system() == 'Windows':
    # Use UTF-8 encoding for Windows console
    console_handler = logging.StreamHandler(sys.stdout)
    try:
        # Try to set UTF-8 encoding (Python 3.7+)
        console_handler.stream.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        # Fallback for older Python versions
        pass
    log_handlers.append(console_handler)
else:
    # Standard handler for Linux/Mac
    log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    try:
        # Load configuration
        config = Config()
        
        # Initialize database
        db_manager = DatabaseManager()
        await db_manager.init_db()
        
        # Initialize and start the bot
        bot = ViewBoosterBot(config, db_manager)
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
