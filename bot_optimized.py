"""
Optimized Bot Implementation for Massive Scale (2000+ accounts)
Integrates PostgreSQL, lazy loading, and advanced rate limiting
"""
import asyncio
import logging
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from config import Config
from database_pg import PostgreSQLManager
from telethon_manager_optimized import OptimizedTelethonManager
from handlers.admin import AdminHandler
from handlers.user import UserHandler
from keyboards import BotKeyboards

logger = logging.getLogger(__name__)

class OptimizedViewBoosterBot:
    """Optimized bot for massive scale operations"""
    
    def __init__(self, config: Config, db_manager: PostgreSQLManager, telethon_manager: OptimizedTelethonManager):
        self.config = config
        self.db = db_manager
        self.telethon_manager = telethon_manager
        
        # Initialize bot with optimized settings
        self.bot = Bot(token=config.BOT_TOKEN)
        
        # Use memory storage for FSM (can be upgraded to Redis for clustering)
        storage = MemoryStorage()
        self.dp = Dispatcher(storage=storage)
        
        # Initialize handlers with optimized components
        self.admin_handler = AdminHandler(self.bot, self.db, self.telethon_manager, self.config)
        self.user_handler = UserHandler(self.bot, self.db, self.telethon_manager, self.config)
        
        # Setup handlers
        self._setup_handlers()
        
        logger.info("Optimized bot initialized for massive scale operations")
    
    def _setup_handlers(self):
        """Setup optimized message and callback handlers"""
        # Command handlers
        self.dp.message.register(self.start_command, commands=['start'])
        self.dp.message.register(self.help_command, commands=['help'])
        self.dp.message.register(self.stats_command, commands=['stats'])
        
        # Callback handlers
        self.dp.callback_query.register(self.handle_callback)
        
        # Text message handlers with intelligent routing
        self.dp.message.register(self.handle_text_message, 
                               lambda message: message.text and not message.text.startswith('/') and 
                               message.from_user and self.config.is_admin(message.from_user.id))
    
    async def start_command(self, message: types.Message):
        """Handle /start command - Admin only with enhanced info"""
        if not message.from_user:
            return
        
        user_id = message.from_user.id
        if not self.config.is_admin(user_id):
            await message.answer("❌ Access denied. Personal use only.")
            return
        
        # Add user to database
        await self.db.add_user(user_id)
        
        # Get system statistics
        stats = await self.telethon_manager.get_account_health_stats()
        
        welcome_text = f"""
🤖 **Massive Scale Telegram View Booster Bot**

📊 **System Status:**
• Total Accounts: {stats.get('total_accounts', 0)}
• Active Accounts: {stats.get('active_accounts', 0)}
• Active Clients: {stats.get('active_clients', 0)}/{self.config.MAX_ACTIVE_CLIENTS}
• Database: PostgreSQL (High Performance)

🚀 **Optimizations Active:**
• Lazy Loading: ✅ (Load clients on demand)
• Connection Pooling: ✅ (DB Pool: {self.config.DB_POOL_SIZE}-{self.config.DB_MAX_POOL_SIZE})
• Rate Limiting: ✅ (Global + Per Account)
• Resource Management: ✅ (Auto cleanup)

**Ready for massive scale operations!**
        """
        
        await message.answer(
            welcome_text,
            reply_markup=BotKeyboards.main_menu(True),
            parse_mode="Markdown"
        )
    
    async def help_command(self, message: types.Message):
        """Enhanced help command with massive scale info"""
        if not message.from_user or not self.config.is_admin(message.from_user.id):
            await message.answer("❌ Access denied.")
            return
        
        help_text = f"""
🆘 **Massive Scale Bot Help**

**📈 Scale Capabilities:**
• Supports up to 2000+ accounts
• PostgreSQL for high performance
• Lazy loading (only active accounts in memory)
• Advanced rate limiting and batch processing

**🎯 Main Features:**
• `/start` - Show system status and main menu
• `/stats` - Detailed system statistics
• Add accounts in batches
• Boost with all accounts automatically
• Intelligent account rotation

**⚡ Performance Features:**
• Max Active Clients: {self.config.MAX_ACTIVE_CLIENTS}
• Batch Size: {self.config.BATCH_SIZE}
• Max Accounts per Operation: {self.config.MAX_ACCOUNTS_PER_OPERATION}
• Auto cleanup every {self.config.CLIENT_CLEANUP_INTERVAL}s

**🔧 Rate Limits:**
• Per Account: {self.config.CALLS_PER_MINUTE_PER_ACCOUNT}/min
• Global: {self.config.GLOBAL_CALLS_PER_MINUTE}/min

The bot automatically manages resources and scales efficiently!
        """
        
        await message.answer(help_text, parse_mode="Markdown")
    
    async def stats_command(self, message: types.Message):
        """Comprehensive statistics for massive scale operations"""
        if not message.from_user or not self.config.is_admin(message.from_user.id):
            await message.answer("❌ Access denied.")
            return
        
        # Get comprehensive stats
        stats = await self.telethon_manager.get_account_health_stats()
        user_channels = await self.db.get_user_channels(message.from_user.id)
        
        stats_text = f"""
📊 **Massive Scale System Statistics**

**🔢 Account Statistics:**
• Total Accounts: {stats.get('total_accounts', 0)}
• Active: {stats.get('active_accounts', 0)}
• Banned: {stats.get('banned_accounts', 0)}
• Flood Wait: {stats.get('flood_wait_accounts', 0)}
• Inactive: {stats.get('inactive_accounts', 0)}

**💻 Performance Metrics:**
• Active Clients: {stats.get('active_clients', 0)}/{self.config.MAX_ACTIVE_CLIENTS}
• Failed Accounts: {stats.get('failed_accounts_count', 0)}
• Rate Limiters: {stats.get('rate_limiters_active', 0)}

**📺 Channel Statistics:**
• Your Channels: {len(user_channels)}
• Total Account Joins: {sum(ch.get('account_count', 0) for ch in user_channels)}
• Total Boosts: {sum(ch.get('total_boosts', 0) for ch in user_channels)}

**⚙️ Configuration:**
• DB Pool: {self.config.DB_POOL_SIZE}-{self.config.DB_MAX_POOL_SIZE}
• Batch Size: {self.config.BATCH_SIZE}
• Cleanup Interval: {self.config.CLIENT_CLEANUP_INTERVAL}s

**System optimized for massive scale operations!** 🚀
        """
        
        await message.answer(stats_text, parse_mode="Markdown")
    
    async def handle_callback(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Enhanced callback handling with performance monitoring"""
        if not callback_query.from_user:
            await callback_query.answer("❌ Invalid request")
            return
        
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        try:
            # Admin handlers - expanded for massive scale operations
            admin_prefixes = ('admin_', 'logs_', 'account_details:', 'premium_', 'channel_', 'stats_')
            admin_exact_matches = [
                'add_account', 'remove_account', 'list_accounts', 'refresh_accounts', 
                'api_default', 'api_custom', 'cancel_operation', 'system_stats',
                'cleanup_resources', 'batch_operations'
            ]
            
            if self.config.is_admin(user_id) and (data.startswith(admin_prefixes) or data in admin_exact_matches):
                await self.admin_handler.handle_callback(callback_query, state)
                return
            
            # User handlers (admin-only mode with enhanced features)
            if self.config.is_admin(user_id):
                await self.user_handler.handle_callback(callback_query, state)
            else:
                await callback_query.answer("❌ Access denied. Personal use only.", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await callback_query.answer("❌ An error occurred. Please try again.", show_alert=True)
    
    async def handle_text_message(self, message: types.Message, state: FSMContext):
        """Enhanced text message routing with performance optimization"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        
        try:
            current_state = await state.get_state()
            message_text = message.text.strip()
            logger.debug(f"📨 Text message from {user_id}: '{message_text}' | State: {current_state}")
            
            # Enhanced routing logic
            if current_state:
                if 'UserStates' in str(current_state):
                    await self.user_handler.handle_message(message, state)
                elif 'AdminStates' in str(current_state):
                    await self.admin_handler.handle_message(message, state)
                else:
                    # Default to user handler for backward compatibility
                    await self.user_handler.handle_message(message, state)
            else:
                # No state - route based on message content
                await self.user_handler.handle_message(message, state)
                
        except Exception as e:
            logger.error(f"Error routing text message: {e}")
            await message.answer("❌ An error occurred processing your message. Please try again.")
    
    async def start(self):
        """Start the optimized bot with enhanced monitoring"""
        try:
            logger.info("🚀 Starting massive scale Telegram View Booster Bot...")
            
            # Pre-flight checks
            await self._perform_startup_checks()
            
            # Start polling with optimized settings
            logger.info("✅ Bot started successfully with massive scale optimizations!")
            await self.dp.start_polling(
                self.bot,
                polling_timeout=30,  # Optimized for performance
                handle_signals=False  # Handled by main runner
            )
            
        except Exception as e:
            logger.error(f"❌ Error starting bot: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def _perform_startup_checks(self):
        """Perform comprehensive startup checks for massive scale readiness"""
        logger.info("🔍 Performing startup checks...")
        
        # Check database connection
        try:
            stats = await self.db.get_account_statistics()
            logger.info(f"✅ Database check passed - {stats.get('total_accounts', 0)} accounts in database")
        except Exception as e:
            logger.error(f"❌ Database check failed: {e}")
            raise
        
        # Check Telethon manager
        try:
            health_stats = await self.telethon_manager.get_account_health_stats()
            logger.info(f"✅ Telethon manager check passed - {health_stats.get('active_accounts', 0)} active accounts")
        except Exception as e:
            logger.error(f"❌ Telethon manager check failed: {e}")
            raise
        
        # Log configuration
        logger.info(f"✅ Configuration loaded:")
        logger.info(f"   • Max Active Clients: {self.config.MAX_ACTIVE_CLIENTS}")
        logger.info(f"   • DB Pool Size: {self.config.DB_POOL_SIZE}-{self.config.DB_MAX_POOL_SIZE}")
        logger.info(f"   • Batch Size: {self.config.BATCH_SIZE}")
        logger.info(f"   • Max Accounts per Operation: {self.config.MAX_ACCOUNTS_PER_OPERATION}")
        
        logger.info("🎯 All startup checks passed - Ready for massive scale operations!")
    
    async def cleanup(self):
        """Enhanced cleanup for massive scale operations"""
        logger.info("🧹 Starting bot cleanup...")
        
        try:
            # Close bot session
            if hasattr(self.bot, 'session') and self.bot.session:
                await self.bot.session.close()
            
            logger.info("✅ Bot cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Error during bot cleanup: {e}")