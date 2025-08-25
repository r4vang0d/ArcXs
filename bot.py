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
from telethon_manager import TelethonManager
from keyboards import BotKeyboards
from handlers.admin import AdminHandler
from handlers.user import UserHandler

logger = logging.getLogger(__name__)

class ViewBoosterBot:
    """Main bot class"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        
        # Initialize Aiogram bot
        self.bot = Bot(token=config.BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Initialize Telethon manager
        self.telethon_manager = TelethonManager(config, db_manager)
        
        # Initialize handlers
        self.admin_handler = AdminHandler(config, db_manager, self.telethon_manager)
        self.user_handler = UserHandler(config, db_manager, self.telethon_manager)
        
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
        
        # Message handlers for FSM states
        self.dp.message.register(self.handle_phone_input, 
                               lambda message: message.text and not message.text.startswith('/'))
    
    async def start_command(self, message: types.Message):
        """Handle /start command"""
        user_id = message.from_user.id
        
        # Add user to database if not exists
        await self.db.add_user(user_id)
        
        # Check if user is admin
        is_admin = self.config.is_admin(user_id)
        
        welcome_text = f"""
🚀 **Welcome to View Booster Bot!**

Hello {message.from_user.first_name}! 

This bot helps you manage Telegram channels and boost views using multiple accounts.

{'🔧 **Admin Features:**' if is_admin else '👤 **User Features:**'}
{'• Manage Telethon accounts' if is_admin else '• Add channels for boosting'}
{'• Monitor system health' if is_admin else '• Boost channel views'}
{'• View detailed logs' if is_admin else '• Track your statistics'}
{'• User management' if is_admin else '• Configure settings'}

{'Choose an option below:' if is_admin else 'Get started by adding a channel!'}
        """
        
        await message.answer(
            welcome_text,
            reply_markup=BotKeyboards.main_menu(is_admin),
            parse_mode="Markdown"
        )
    
    async def help_command(self, message: types.Message):
        """Handle /help command"""
        help_text = """
📚 **Bot Commands:**

/start - Start the bot and show main menu
/help - Show this help message
/stats - Show your statistics

🔧 **How to use:**

1️⃣ **Add Channel**: Use the "Add Channel" button to add channels you want to boost
2️⃣ **Boost Views**: Select a channel and boost its message views
3️⃣ **Settings**: Customize boost behavior and delays
4️⃣ **Stats**: Track your boost history and results

📱 **Supported Links:**
• https://t.me/channel_name
• https://t.me/joinchat/invite_code
• @channel_name
• channel_name

⚙️ **Settings Options:**
• Views Only vs Views + Read
• Account Rotation ON/OFF
• Delay levels (Low/Medium/High)

❓ Need help? Contact the bot administrator.
        """
        
        await message.answer(help_text, parse_mode="Markdown")
    
    async def stats_command(self, message: types.Message):
        """Handle /stats command"""
        user_id = message.from_user.id
        
        # Get user statistics
        channels = await self.db.get_user_channels(user_id)
        total_channels = len(channels)
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        
        # Check if premium
        is_premium = await self.db.is_premium_user(user_id)
        
        stats_text = f"""
📊 **Your Statistics**

👤 **Account Type**: {'Premium ⭐' if is_premium else 'Free 🆓'}
📢 **Channels**: {total_channels}{'/' + ('∞' if is_premium else '1')}
⚡ **Total Boosts**: {total_boosts:,}

📈 **Recent Activity:**
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
    
    async def handle_callback(self, callback_query: types.CallbackQuery, state: FSMContext = None):
        """Handle all callback queries"""
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        try:
            # Admin handlers
            if self.config.is_admin(user_id) and data.startswith(('admin_', 'add_account', 'remove_account', 'list_accounts', 'refresh_accounts')):
                await self.admin_handler.handle_callback(callback_query, state)
                return
            
            # User handlers
            await self.user_handler.handle_callback(callback_query, state)
            
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await callback_query.answer("❌ An error occurred. Please try again.", show_alert=True)
    
    async def handle_phone_input(self, message: types.Message, state: FSMContext):
        """Handle text input (for FSM states)"""
        user_id = message.from_user.id
        
        # Check if this is admin input
        if self.config.is_admin(user_id):
            await self.admin_handler.handle_message(message, state)
            return
        
        # Handle user input
        await self.user_handler.handle_message(message, state)
    
    async def start(self):
        """Start the bot"""
        try:
            logger.info("Starting View Booster Bot...")
            
            # Load existing Telethon sessions
            await self.telethon_manager.load_existing_sessions()
            
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
            await self.telethon_manager.cleanup()
            await self.bot.session.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        logger.info("Bot shutdown complete")
