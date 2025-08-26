"""
Main bot class for the Telegram View Booster Bot
Combines Aiogram and Telethon functionality
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config
from database import DatabaseManager
from session_manager import TelethonManager
from inline_keyboards import BotKeyboards
from handlers.admin import AdminHandler
from handlers.user import UserHandler
from live_monitor_service import LiveMonitorService

logger = logging.getLogger(__name__)

class ViewBoosterBot:
    """Main bot class"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        
        # Initialize Aiogram bot with proper token validation
        if not config.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        self.bot = Bot(token=config.BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Initialize Telethon manager
        self.telethon_manager = TelethonManager(config, db_manager)
        
        # Initialize live monitoring service
        self.live_monitor = LiveMonitorService(db_manager, self.telethon_manager)
        
        # Initialize handlers with live monitor service
        self.admin_handler = AdminHandler(config, db_manager, self.telethon_manager)
        self.user_handler = UserHandler(config, db_manager, self.telethon_manager, self.live_monitor)
        
        # Pass bot instance to handlers
        self.admin_handler.bot = self.bot
        self.user_handler.bot = self.bot
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all bot handlers"""
        
        # Command handlers
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.help_command, Command("help"))
        self.dp.message.register(self.stats_command, Command("stats"))
        
        # Callback handlers
        self.dp.callback_query.register(self.handle_callback)
        
        # All text message handling - simplified filter
        self.dp.message.register(self.handle_text_message, 
                               lambda message: message.text and not message.text.startswith('/') and message.from_user and self.config.is_admin(message.from_user.id))
    
    async def start_command(self, message: types.Message):
        """Handle /start command - Admin only"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        
        # Check if user is admin - block non-admins
        if not self.config.is_admin(user_id):
            await message.answer(
                "🚫 **ARCX - Access Restricted**\n\n⚠️ This is a premium personal bot.\n🔐 Authorized users only.",
                parse_mode="Markdown"
            )
            return
        
        # Add admin to database if not exists (with all premium features)
        await self.db.add_user(user_id, premium=True)
        
        welcome_text = f"""
═══════════════════════════════════

                **🚀 A R C X 🚀**
        **The Ultimate View Booster**

═══════════════════════════════════

👋 **Welcome back, {message.from_user.first_name or 'Admin'}!**

✨ **Premium Features Unlocked:**

🎯 **Channel Management** - Add unlimited channels
⚡ **Instant Boosting** - Boost views in real-time  
🎭 **Smart Reactions** - Auto emoji reactions
📊 **Advanced Analytics** - Detailed performance stats
📱 **Account Control** - Manage multiple accounts
💚 **Health Monitoring** - System status tracking
🔴 **Live Management** - Real-time monitoring
🗳️ **Poll Automation** - Automated poll voting

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎛️ **Ready to dominate your channels?**
        """
        
        await message.answer(
            welcome_text,
            reply_markup=BotKeyboards.main_menu(True),
            parse_mode="Markdown"
        )
    
    async def help_command(self, message: types.Message):
        """Handle /help command - Admin only"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.config.is_admin(user_id):
            await message.answer(
                "🚫 **ARCX - Access Restricted**\n\n⚠️ This is a premium personal bot.\n🔐 Authorized users only.",
                parse_mode="Markdown"
            )
            return
        
        help_text = """
═══════════════════════════════════

                **🚀 A R C X 🚀**
           **Help & Documentation**

═══════════════════════════════════

🎮 **Quick Commands:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• `/start` - Launch main dashboard
• `/help` - Show this help guide  
• `/stats` - View performance metrics

🎯 **Core Features Guide:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📢 Channel Management**
• Add unlimited channels instantly
• Support for all Telegram link formats
• Bulk channel operations

**⚡ Smart Boosting**
• Real-time view boosting
• Intelligent account rotation
• Customizable delay settings

**📊 Advanced Analytics**
• Detailed boost statistics
• Account health monitoring
• Performance tracking

**🎭 Automation Suite**
• Auto emoji reactions
• Poll voting automation
• Live monitoring system

🔗 **Supported Formats:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• `https://t.me/channel_name`
• `https://t.me/joinchat/code`
• `@channel_name`
• `channel_name`

⚙️ **Performance Modes:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 🚀 **Fast Mode** - Maximum speed
• ⚡ **Balanced** - Optimal performance
• 🛡️ **Safe Mode** - Maximum security

✨ **Unlimited Access** - All premium features enabled
        """
        
        await message.answer(help_text, parse_mode="Markdown")
    
    async def stats_command(self, message: types.Message):
        """Handle /stats command - Admin only"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.config.is_admin(user_id):
            await message.answer(
                "🚫 **ARCX - Access Restricted**\n\n⚠️ This is a premium personal bot.\n🔐 Authorized users only.",
                parse_mode="Markdown"
            )
            return
        
        # Get user statistics
        channels = await self.db.get_user_channels(user_id)
        total_channels = len(channels)
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        
        stats_text = f"""
═══════════════════════════════════

                **🚀 A R C X 🚀**
          **Performance Dashboard**

═══════════════════════════════════

👤 **Account Status:** Premium Admin ⭐
📢 **Channels Managed:** {total_channels} (Unlimited)
⚡ **Total Boosts Delivered:** {total_boosts:,}

📈 **Recent Channel Activity:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        
        # Add recent channels
        if channels:
            stats_text += "\n"
            for channel in channels[-5:]:  # Last 5 channels
                name = channel.get("title") or channel["channel_link"]
                boosts = channel.get("total_boosts", 0)
                stats_text += f"📢 {name}: {boosts} boosts\n"
        else:
            stats_text += "\nNo channels added yet. Use /start to get started!"
        
        await message.answer(stats_text, parse_mode="Markdown")
    
    async def handle_callback(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle all callback queries"""
        if not callback_query.from_user or not callback_query.data:
            await callback_query.answer("Invalid request", show_alert=True)
            return
        
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        try:
            # Admin handlers - expanded to include premium and channel control callbacks
            admin_prefixes = ('admin_', 'logs_', 'account_details:', 'premium_', 'channel_')
            admin_exact_matches = ['add_account', 'remove_account', 'list_accounts', 'refresh_accounts', 'api_default', 'api_custom', 'cancel_operation']
            
            if self.config.is_admin(user_id) and (data.startswith(admin_prefixes) or data in admin_exact_matches):
                await self.admin_handler.handle_callback(callback_query, state)
                return
            
            # User handlers (admin-only mode)
            if self.config.is_admin(user_id):
                await self.user_handler.handle_callback(callback_query, state)
            else:
                await callback_query.answer("🚫 ARCX - Access Restricted. Authorized users only.", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await callback_query.answer("❌ An error occurred. Please try again.", show_alert=True)
    
    async def handle_text_message(self, message: types.Message, state: FSMContext):
        """Handle all text input routing to appropriate handlers"""
        if not message.from_user:
            return
        user_id = message.from_user.id
        
        try:
            current_state = await state.get_state()
            message_text = message.text.strip() if message.text else ""
            logger.info(f"📨 Text message received from {user_id}: '{message_text}' | State: {current_state}")
            
            # Always try user handler first since most operations are user-related
            await self.user_handler.handle_message(message, state)
            
            # If user handler didn't handle it, try admin handler
            if current_state and 'AdminStates' in str(current_state):
                logger.info("🔄 Trying admin handler as fallback")
                await self.admin_handler.handle_message(message, state)
                
        except Exception as e:
            logger.error(f"Error routing text message: {e}")
            await message.answer("❌ An error occurred processing your message. Please try again.")
    
    async def start(self):
        """Start the bot"""
        try:
            logger.info("Starting View Booster Bot...")
            
            # Load existing Telethon sessions
            await self.telethon_manager.load_existing_sessions()
            
            # Start live monitoring service only if there are monitors configured
            # This prevents auto-start spam when no channels are being monitored
            # await self.live_monitor.start_monitoring()
            
            # Start polling
            logger.info("Bot started successfully!")
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            # Cleanup on shutdown
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources on shutdown"""
        logger.info("Shutting down bot...")
        
        try:
            # Stop live monitoring service
            await self.live_monitor.stop_monitoring()
            await self.telethon_manager.cleanup()
            await self.bot.session.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        logger.info("Bot shutdown complete")
