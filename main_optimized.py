"""
Optimized Main Entry Point for Massive Scale Telegram View Booster Bot
Supports 2000+ accounts with PostgreSQL, lazy loading, and advanced rate limiting
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_optimized.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Import optimized components
try:
    from config import Config
    from database_pg import PostgreSQLManager
    from telethon_manager_optimized import OptimizedTelethonManager
    from bot_optimized import OptimizedViewBoosterBot
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

class MassiveScaleBotRunner:
    """Main application runner for massive scale operations"""
    
    def __init__(self):
        self.config = None
        self.db_manager = None
        self.telethon_manager = None
        self.bot = None
        self.cleanup_task = None
        
    async def initialize(self):
        """Initialize all components"""
        try:
            # Load configuration
            logger.info("Loading configuration...")
            self.config = Config()
            logger.info(f"Configuration loaded - Max active clients: {self.config.MAX_ACTIVE_CLIENTS}")
            
            # Initialize PostgreSQL database with connection pooling
            logger.info("Initializing PostgreSQL database with connection pooling...")
            self.db_manager = PostgreSQLManager(
                database_url=self.config.DATABASE_URL,
                pool_size=self.config.DB_POOL_SIZE,
                max_pool_size=self.config.DB_MAX_POOL_SIZE
            )
            await self.db_manager.init_pool()
            
            # Initialize optimized Telethon manager
            logger.info("Initializing optimized Telethon manager...")
            self.telethon_manager = OptimizedTelethonManager(self.config, self.db_manager)
            
            # Initialize optimized bot
            logger.info("Initializing optimized bot...")
            self.bot = OptimizedViewBoosterBot(self.config, self.db_manager, self.telethon_manager)
            
            # Start periodic cleanup task
            self.cleanup_task = asyncio.create_task(self._periodic_maintenance())
            
            logger.info("✅ All components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            await self.cleanup()
            raise
    
    async def _periodic_maintenance(self):
        """Periodic maintenance tasks for massive scale operations"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                logger.info("🔧 Running periodic maintenance...")
                
                # Clean up old logs
                await self.db_manager.cleanup_old_logs(self.config.LOG_CLEANUP_DAYS)
                
                # Get and log statistics
                stats = await self.telethon_manager.get_account_health_stats()
                logger.info(f"📊 Account Stats: {stats}")
                
                # Force garbage collection for memory optimization
                import gc
                gc.collect()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic maintenance: {e}")
    
    async def start(self):
        """Start the bot"""
        try:
            await self.initialize()
            logger.info("🚀 Starting massive scale Telegram View Booster Bot...")
            await self.bot.start()
        except KeyboardInterrupt:
            logger.info("👋 Received shutdown signal")
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup all resources"""
        logger.info("🧹 Cleaning up resources...")
        
        try:
            if self.cleanup_task and not self.cleanup_task.done():
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
            
            if self.telethon_manager:
                await self.telethon_manager.cleanup()
            
            if self.db_manager:
                await self.db_manager.close()
                
            logger.info("✅ Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

def setup_signal_handlers(runner):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        # Create new event loop for cleanup if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(runner.cleanup())
            else:
                loop.run_until_complete(runner.cleanup())
        except Exception as e:
            logger.error(f"Error in signal handler: {e}")
        finally:
            sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point"""
    runner = MassiveScaleBotRunner()
    setup_signal_handlers(runner)
    
    try:
        await runner.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        logger.error("Python 3.8+ is required for massive scale operations")
        sys.exit(1)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)