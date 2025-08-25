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

from bot import ViewBoosterBot
from config import Config
from database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
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
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
