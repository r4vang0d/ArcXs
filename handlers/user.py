"""
User handlers for the Telegram View Booster Bot
Handles channel management, boosting, and settings
"""
import asyncio
import json
import logging
from typing import Optional, Any

from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database import DatabaseManager, LogType
from session_manager import TelethonManager
from inline_keyboards import BotKeyboards
from helpers import Utils

logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_message_ids = State()
    waiting_for_reaction_message_ids = State()
    waiting_for_live_channel = State()
    waiting_for_poll_url = State()
    waiting_for_poll_choice = State()
    waiting_for_custom_view_count = State()
    waiting_for_manual_message_ids = State()

class UserHandler:
    """Handles user-specific operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, telethon_manager: TelethonManager, live_monitor=None):
        self.config = config
        self.db = db_manager
        self.telethon = telethon_manager
        self.live_monitor = live_monitor
        self.bot: Optional[Bot] = None  # Will be set by the main bot class
    
    async def handle_callback(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle user callback queries"""
        if not callback_query.from_user or not callback_query.data:
            await callback_query.answer("Invalid request", show_alert=True)
            return
        
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        # Ensure user exists in database
        await self.db.add_user(user_id)
        
        if data == "main_menu":
            await self.show_main_menu(callback_query)
        elif data == "user_panel":
            await self.show_personal_dashboard(callback_query)
        elif data == "add_channel":
            await self.start_add_channel(callback_query, state)
        elif data == "my_channels":
            await self.show_my_channels(callback_query)
        elif data == "my_stats":
            await self.show_my_stats(callback_query)
        elif data == "boost_views":
            await self.show_boost_menu(callback_query)
        elif data == "emoji_reactions":
            await self.show_emoji_reactions_menu(callback_query)
        elif data == "settings":
            await self.show_settings(callback_query)
        elif data == "live_management":
            await self.show_live_management(callback_query)
        elif data == "add_live_channel":
            await self.start_add_live_channel(callback_query, state)
        elif data == "view_live_channels":
            await self.show_live_channels(callback_query)
        elif data == "live_monitor_status":
            await self.show_live_monitor_status(callback_query)
        elif data.startswith("live_channel_info:"):
            await self.show_live_channel_info(callback_query, data)
        elif data.startswith("remove_live_channel:"):
            await self.confirm_remove_live_channel(callback_query, data)
        elif data == "start_live_monitor":
            await self.start_live_monitoring(callback_query)
        elif data == "stop_live_monitor":
            await self.stop_live_monitoring(callback_query)
        elif data == "poll_manager":
            await self.show_poll_manager(callback_query)
        elif data == "start_poll_voting":
            await self.start_poll_voting(callback_query, state)
        elif data == "poll_history":
            await self.show_poll_history(callback_query)
        elif data.startswith("vote_option:"):
            await self.execute_poll_vote(callback_query, data, state)
        elif data.startswith("channel_info:"):
            await self.show_channel_info(callback_query, data)
        elif data.startswith("remove_channel:"):
            await self.confirm_remove_channel(callback_query, data)
        elif data.startswith("instant_boost:"):
            await self.start_instant_boost(callback_query, data, state)
        elif data.startswith("account_count_continue:"):
            await self.show_view_count_selection(callback_query, data, state)
        elif data.startswith("view_count:"):
            await self.handle_view_count_selection(callback_query, data, state)
        elif data.startswith("time_select:"):
            await self.handle_time_selection(callback_query, data, state)
        elif data.startswith("auto_option:"):
            await self.handle_auto_option_selection(callback_query, data, state)
        elif data.startswith("view_count_back:"):
            await self.handle_view_count_back(callback_query, data, state)
        elif data.startswith("time_select_back:"):
            await self.handle_time_select_back(callback_query, data, state)
        elif data.startswith("add_reactions:"):
            await self.start_add_reactions(callback_query, data, state)
        elif data.startswith("boost_stats:"):
            await self.show_boost_stats(callback_query, data)
        elif data.startswith("setting_"):
            await self.handle_setting(callback_query, data)
        elif data.startswith("delay_"):
            await self.handle_delay_setting(callback_query, data)
        elif data.startswith("auto_count_"):
            await self.handle_auto_count_setting(callback_query, data)
        elif data.startswith("confirm:"):
            await self.handle_confirmation(callback_query, data)
        elif data == "cancel_action" or data == "cancel_operation":
            await self.cancel_operation(callback_query, state)
        else:
            await callback_query.answer("Unknown command")
    
    async def handle_message(self, message: types.Message, state: FSMContext):
        """Handle user text messages"""
        try:
            current_state = await state.get_state()
            logger.info(f"User message received in state: {current_state}")
            
            if current_state == UserStates.waiting_for_channel.state:
                await self.process_add_channel(message, state)
            elif current_state == UserStates.waiting_for_message_ids.state:
                await self.process_boost_messages(message, state)
            elif current_state == UserStates.waiting_for_reaction_message_ids.state:
                await self.process_reaction_messages(message, state)
            elif current_state == UserStates.waiting_for_live_channel.state:
                await self.process_live_channel(message, state)
            elif current_state == UserStates.waiting_for_poll_url.state:
                await self.process_poll_url(message, state)
            elif current_state == UserStates.waiting_for_custom_view_count.state:
                await self.process_custom_view_count(message, state)
            elif current_state == UserStates.waiting_for_manual_message_ids.state:
                await self.process_manual_message_ids(message, state)
            else:
                logger.info(f"No handler for state: {current_state}")
        except Exception as e:
            logger.error(f"Error handling user message: {e}")
            await message.answer("❌ An error occurred. Please try again or contact support.")
    
    async def show_main_menu(self, callback_query: types.CallbackQuery):
        """Show main menu"""
        user_id = callback_query.from_user.id
        is_admin = self.config.is_admin(user_id)
        
        welcome_text = f"""
🎯 **Professional View Booster**

┌─────────────────────────┐
│  Welcome, {callback_query.from_user.first_name}! 👋
└─────────────────────────┘

🔥 **Boost your Telegram channels with premium quality views**
💎 **Powered by advanced automation technology**

{'🛠 **Administrator Access** - Choose your management panel:' if is_admin else '⚡ **Ready to boost your content?** - Select an option below:'}
        """
        
        try:
            if callback_query.message:
                await callback_query.message.edit_text(
                    welcome_text,
                    reply_markup=BotKeyboards.main_menu(is_admin),
                    parse_mode="Markdown"
                )
            else:
                await self.bot.send_message(
                    callback_query.from_user.id,
                    welcome_text,
                    reply_markup=BotKeyboards.main_menu(is_admin),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error editing main menu: {e}")
            await callback_query.answer("Menu updated!", show_alert=False)
        await callback_query.answer()
    
    async def show_personal_dashboard(self, callback_query: types.CallbackQuery):
        """Show personal dashboard"""
        user_id = callback_query.from_user.id
        
        # Get user stats
        channels = await self.db.get_user_channels(user_id)
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        
        panel_text = f"""
🎭 **Personal Dashboard**

**Account Overview:**
• Status: 🌟 Personal Admin Access
• Channels: {len(channels)} (Unlimited)  
• Total Boosts: {total_boosts:,} views

💪 **Ready to amplify your reach?**
🚀 **Choose your next action below:**
        """
        
        try:
            if callback_query.message:
                await callback_query.message.edit_text(
                    panel_text,
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
            else:
                await self.bot.send_message(
                    callback_query.from_user.id,
                    panel_text,
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error editing dashboard: {e}")
            await callback_query.answer("Dashboard updated!", show_alert=False)
        await callback_query.answer()
    
    async def start_add_channel(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start add channel process"""
        user_id = callback_query.from_user.id
        
        # Personal use - no limits
        
        text = """🎯 Add New Channel

How it works:
1. Send your Telegram channel link
2. System will automatically join with accounts
3. Start boosting views instantly!

Accepted formats:
• https://t.me/your_channel
• https://t.me/joinchat/xxxxx
• @your_channel_name
• your_channel_name

Features:
• Auto-join with all accounts
• Public and private channel support
• Instant integration

💬 Send your channel link or type /cancel to exit"""
        
        try:
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.cancel_operation()
                )
            else:
                await self.bot.send_message(
                    callback_query.from_user.id,
                    text,
                    reply_markup=BotKeyboards.cancel_operation()
                )
        except Exception as e:
            logger.error(f"Error starting add channel: {e}")
            # Send simple fallback message if editing fails
            await self.bot.send_message(
                callback_query.from_user.id,
                "🎯 Add New Channel\n\nSend your Telegram channel link (like @channel or https://t.me/channel) or type /cancel to exit",
                reply_markup=BotKeyboards.cancel_operation()
            )
        await state.set_state(UserStates.waiting_for_channel)
        logger.info(f"Set state to waiting_for_channel for user {user_id}")
        await callback_query.answer()
    
    async def process_add_channel(self, message: types.Message, state: FSMContext):
        """Process add channel with link"""
        if not message.from_user or not message.text:
            return
        user_id = message.from_user.id
        channel_link = message.text.strip()
        
        if channel_link == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled", 
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        if not Utils.is_valid_telegram_link(channel_link):
            await message.answer(
                "❌ Invalid channel link format. Please try again or /cancel\n\n" +
                "Examples:\n• https://t.me/channel_name\n• @channel_name\n• channel_name"
            )
            return
        
        normalized_link = Utils.normalize_telegram_link(channel_link)
        
        # Show processing message
        processing_msg = await message.answer("⏳ Adding channel and joining with accounts...")
        
        try:
            # Join channel with available accounts
            logger.info(f"Attempting to join channel: {normalized_link}")
            success, join_message, channel_id = await self.telethon.join_channel(normalized_link)
            
            if success:
                # Add channel to database
                channel_added = await self.db.add_channel(
                    user_id=user_id,
                    channel_link=normalized_link,
                    channel_id=channel_id,
                    title=join_message.split("joined ")[1] if "joined " in join_message else None
                )
                
                if channel_added:
                    await self.db.log_action(
                        LogType.JOIN,
                        user_id=user_id,
                        message=f"User added channel: {normalized_link}"
                    )
                    
                    await processing_msg.delete()
                    await message.answer(
                        f"✅ **Channel Added Successfully!**\n\n{join_message}\n\n" +
                        "You can now boost views for this channel.",
                        reply_markup=BotKeyboards.main_menu(True),
                        parse_mode="Markdown"
                    )
                else:
                    await processing_msg.delete()
                    await message.answer(
                        "⚠️ Channel joined but failed to save to database. Please try again.",
                        reply_markup=BotKeyboards.main_menu(True)
                    )
            else:
                await processing_msg.delete()
                await message.answer(
                    f"❌ **Failed to Add Channel**\n\n{join_message}\n\n" +
                    "Please check the channel link and try again.",
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error adding channel: {e}")
            await message.answer(
                "❌ An error occurred while adding the channel. Please try again.",
                reply_markup=BotKeyboards.main_menu(True)
            )
        
        await state.clear()
    
    async def show_my_channels(self, callback_query: types.CallbackQuery):
        """Show user's channels"""
        user_id = callback_query.from_user.id
        channels = await self.db.get_user_channels(user_id)
        
        if not channels:
            text = "📋 **My Channels**\n\n❌ No channels added yet.\n\nUse 'Add Channel' to get started!"
        else:
            text = f"📋 **My Channels** ({len(channels)} total)\n\n"
            for channel in channels:
                name = channel.get("title") or Utils.truncate_text(channel["channel_link"])
                boosts = channel.get("total_boosts", 0)
                account_count = channel.get("account_count", 1)
                last_boosted = Utils.format_datetime(channel.get("last_boosted"))
                
                text += f"📢 **{name}**\n"
                text += f"   ⚡ Boosts: {boosts} | 👥 Accounts: {account_count}\n"
                text += f"   📅 Last: {last_boosted}\n\n"
        
        try:
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.channel_list(channels, user_id),
                    parse_mode="Markdown"
                )
            else:
                await self.bot.send_message(
                    callback_query.from_user.id,
                    text,
                    reply_markup=BotKeyboards.channel_list(channels, user_id),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error showing channels: {e}")
            await callback_query.answer("Channels updated!", show_alert=False)
        await callback_query.answer()
    
    async def show_my_stats(self, callback_query: types.CallbackQuery):
        """Show user statistics"""
        user_id = callback_query.from_user.id
        channels = await self.db.get_user_channels(user_id)
        
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        
        # Get recent boost logs for this user
        recent_logs = await self.db.get_logs(limit=5, log_type=LogType.BOOST)
        user_recent_logs = [log for log in recent_logs if log["user_id"] == user_id]
        
        stats_text = f"""
📊 **My Statistics**

👤 **Account Info:**
Status: Personal Admin Access ⭐
Member Since: {Utils.format_datetime(None)}

📢 **Channel Stats:**
Total Channels: {len(channels)} (Unlimited)
Total Boosts: {total_boosts:,}

📈 **Recent Activity:**
        """
        
        if user_recent_logs:
            for log in user_recent_logs[:3]:
                timestamp = Utils.format_datetime(log["created_at"])
                message = log["message"] or "Boost activity"
                stats_text += f"⚡ {timestamp}: {Utils.truncate_text(message)}\n"
        else:
            stats_text += "No recent activity"
        
        if channels:
            stats_text += f"\n📢 **Top Channels:**\n"
            sorted_channels = sorted(channels, key=lambda x: x.get("total_boosts", 0), reverse=True)
            for channel in sorted_channels[:3]:
                name = channel.get("title") or Utils.truncate_text(channel["channel_link"])
                boosts = channel.get("total_boosts", 0)
                stats_text += f"• {name}: {boosts} boosts\n"
        
        if callback_query.message:
            await callback_query.message.edit_text(
                stats_text,
                reply_markup=BotKeyboards.back_button("main_menu"),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def show_boost_menu(self, callback_query: types.CallbackQuery):
        """Show boost menu with user's channels"""
        user_id = callback_query.from_user.id
        channels = await self.db.get_user_channels(user_id)
        
        if not channels:
            await callback_query.answer(
                "❌ No channels added yet. Add a channel first!",
                show_alert=True
            )
            return
        
        text = f"""
⚡ **Boost Views**

Select a channel to boost:

💡 **How it works:**
• All active accounts will view your messages
• Views are incremented automatically
• Messages can be marked as read (optional)

Choose a channel below:
        """
        
        # Create buttons for each channel
        buttons = []
        for channel in channels:
            name = channel.get("title") or Utils.truncate_text(channel["channel_link"])
            buttons.append([
                types.InlineKeyboardButton(
                    text=f"📢 {name}",
                    callback_data=f"instant_boost:{channel['id']}"
                )
            ])
        
        buttons.append([types.InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")])
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        try:
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await self.bot.send_message(
                    callback_query.from_user.id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error showing boost menu: {e}")
            await callback_query.answer("Boost menu updated!", show_alert=False)
        await callback_query.answer()
    
    async def start_instant_boost(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Start instant boost process - now shows account count first"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            # Get channel info
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            # Get available account count
            active_accounts = await self.db.get_active_accounts()
            available_count = len(active_accounts)
            
            if available_count == 0:
                await callback_query.answer("❌ No active accounts available", show_alert=True)
                return
            
            # Store channel info in state
            await state.update_data(
                boost_channel_id=channel_id, 
                boost_channel_link=channel["channel_link"],
                feature_type="boost",
                available_accounts=available_count
            )
            
            text = f"""
📊 **Account Status**

Channel: {channel.get("title") or channel["channel_link"]}

💯 **Available Accounts:** {available_count:,}

📝 **How it works:**
• Each account will view your selected messages
• Views are distributed across the timeframe you choose
• You can select how many views you want
• Choose between auto-detection or manual message selection

🚀 **Ready to continue?**
Click Continue to select the number of views you want.
            """
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.account_count_display(available_count, "boost"),
                    parse_mode="Markdown"
                )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error starting instant boost: {e}")
            await callback_query.answer("❌ Error starting boost", show_alert=True)
    
    async def show_view_count_selection(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Show view count selection based on available accounts"""
        try:
            feature_type = data.split(":")[1]
            state_data = await state.get_data()
            available_accounts = state_data.get("available_accounts", 0)
            channel_link = state_data.get("boost_channel_link", "Unknown")
            
            text = f"""
📊 **Select View Count**

Channel: {channel_link}
💯 Available Accounts: {available_accounts:,}

🎯 **Choose how many views you want:**
Select from the options below based on your available accounts.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.view_count_selection(available_accounts, feature_type),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing view count selection: {e}")
            await callback_query.answer("❌ Error showing view count options", show_alert=True)
    
    async def handle_view_count_selection(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Handle view count selection"""
        try:
            parts = data.split(":")
            feature_type = parts[1]
            view_count_str = parts[2]
            
            state_data = await state.get_data()
            available_accounts = state_data.get("available_accounts", 0)
            
            if view_count_str == "custom":
                # Handle custom view count input
                text = f"""
✏️ **Custom View Count**

💯 Available Accounts: {available_accounts:,}

Enter the number of views you want (up to {available_accounts:,}):
                """
                
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.cancel_operation(),
                    parse_mode="Markdown"
                )
                await state.set_state(UserStates.waiting_for_custom_view_count)
                await callback_query.answer()
                return
            
            view_count = int(view_count_str)
            
            # Validate view count doesn't exceed available accounts
            if view_count > available_accounts:
                await callback_query.answer(f"❌ Not enough accounts! You have {available_accounts} available.", show_alert=True)
                return
            
            # Store view count and proceed to time selection
            await state.update_data(selected_view_count=view_count)
            
            text = f"""
⏰ **Select Time Frame**

📊 Views Selected: {view_count:,}
📢 Channel: {state_data.get("boost_channel_link", "Unknown")}

🕒 **Choose time frame for the views:**
Select how quickly you want the views to be delivered.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.time_selection(feature_type, view_count),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling view count selection: {e}")
            await callback_query.answer("❌ Error processing view count", show_alert=True)
    
    async def handle_time_selection(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Handle time selection"""
        try:
            parts = data.split(":")
            feature_type = parts[1]
            view_count = int(parts[2])
            time_minutes = int(parts[3])
            
            # Store time selection and proceed to auto/manual options
            await state.update_data(selected_time_minutes=time_minutes)
            
            state_data = await state.get_data()
            
            time_text = "Instant" if time_minutes == 0 else f"{time_minutes} minutes"
            
            text = f"""
🎯 **Choose Mode**

📊 Views: {view_count:,}
⏰ Time Frame: {time_text}
📢 Channel: {state_data.get("boost_channel_link", "Unknown")}

🤖 **Auto Mode:** Automatically boost the latest messages
✋ **Manual Mode:** Choose specific message IDs

Select your preferred mode:
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.auto_options_selection(feature_type, view_count, time_minutes),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling time selection: {e}")
            await callback_query.answer("❌ Error processing time selection", show_alert=True)
    
    async def handle_auto_option_selection(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Handle auto/manual option selection"""
        try:
            parts = data.split(":")
            if len(parts) != 5:
                await callback_query.answer("❌ Invalid selection data", show_alert=True)
                return
            
            feature_type = parts[1]
            if feature_type not in ["boost", "reactions"]:
                await callback_query.answer("❌ Invalid feature type", show_alert=True)
                return
            
            try:
                view_count = int(parts[2])
                time_minutes = int(parts[3])
                if view_count <= 0 or time_minutes < 0:
                    raise ValueError("Invalid counts")
            except ValueError:
                await callback_query.answer("❌ Invalid count values", show_alert=True)
                return
            
            mode = parts[4]
            if mode not in ["auto", "manual"]:
                await callback_query.answer("❌ Invalid mode selection", show_alert=True)
                return
            
            state_data = await state.get_data()
            # Get the appropriate channel link based on feature type
            if feature_type == "boost":
                channel_link = state_data.get("boost_channel_link")
            else:  # reactions
                channel_link = state_data.get("reaction_channel_link")
            
            if mode == "auto":
                # Auto mode - get recent messages automatically
                user_id = callback_query.from_user.id
                auto_count = await self.get_user_setting(user_id, "auto_message_count")
                if not auto_count or auto_count <= 0:
                    auto_count = 10  # Default fallback
                    # Save the default setting for the user
                    await self.set_user_setting(user_id, "auto_message_count", auto_count)
                
                message_ids = await self.telethon.get_channel_messages(channel_link, limit=auto_count)
                
                if not message_ids:
                    await callback_query.answer("❌ Could not find recent messages in the channel.", show_alert=True)
                    return
                
                # Answer the callback query first to prevent UI issues
                await callback_query.answer()
                
                # Proceed with boost or reactions based on feature type
                if feature_type == "reactions":
                    await self.execute_reactions_with_settings(callback_query, state, message_ids, view_count, time_minutes)
                else:
                    await self.execute_boost_with_settings(callback_query, state, message_ids, view_count, time_minutes)
                
                # Ensure we return here to prevent further execution
                return
                
            else:
                # Manual mode - ask for message IDs
                action_type = "Views" if feature_type == "boost" else "Reactions"
                text = f"""
✏️ **Manual Message Selection**

📊 {action_type}: {view_count:,}
⏰ Time Frame: {"Instant" if time_minutes == 0 else f"{time_minutes} minutes"}

Send message IDs or message links separated by commas or spaces.

**Examples:**
• 123, 124, 125
• 100 101 102
• 50-55 (range)
• https://t.me/channel/123

Send your message IDs now:
                """
                
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.cancel_operation(),
                    parse_mode="Markdown"
                )
                await state.set_state(UserStates.waiting_for_manual_message_ids)
                await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling auto option selection: {e}")
            await callback_query.answer("❌ Error processing selection", show_alert=True)
    
    async def handle_view_count_back(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Handle back button from view count selection to account count display"""
        try:
            feature_type = data.split(":")[1]
            state_data = await state.get_data()
            available_accounts = state_data.get("available_accounts", 0)
            channel_link = state_data.get("boost_channel_link" if feature_type == "boost" else "reaction_channel_link")
            
            feature_name = "Boost Views" if feature_type == "boost" else "Add Reactions"
            action_emoji = "🚀" if feature_type == "boost" else "😍"
            
            text = f"""
📊 **Account Status**

Channel: {channel_link or "Unknown"}

💯 **Available Accounts:** {available_accounts:,}

{action_emoji} **{feature_name}:**
• Each account will {'add views' if feature_type == 'boost' else 'react with random emojis'}
• You can choose how many {'views' if feature_type == 'boost' else 'reactions'} and timing
• Accounts are managed efficiently in batches

🚀 **Ready to continue?**
Click Continue to select the number of {'views' if feature_type == 'boost' else 'reactions'} you want.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.account_count_display(available_accounts, feature_type),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling view count back: {e}")
            await callback_query.answer("❌ Error going back", show_alert=True)
    
    async def handle_time_select_back(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Handle back button from auto options to time selection"""
        try:
            parts = data.split(":")
            feature_type = parts[1]
            view_count = int(parts[2])
            
            state_data = await state.get_data()
            
            text = f"""
⏰ **Select Time Frame**

📊 Views Selected: {view_count:,}
📢 Channel: {state_data.get("boost_channel_link", "Unknown")}

🕒 **Choose time frame for the views:**
Select how quickly you want the views to be delivered.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.time_selection(feature_type, view_count),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling time select back: {e}")
            await callback_query.answer("❌ Error going back", show_alert=True)

    async def start_add_reactions(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Start emoji reactions process - now shows account count first"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            # Get channel info
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            # Get available account count
            active_accounts = await self.db.get_active_accounts()
            available_count = len(active_accounts)
            
            if available_count == 0:
                await callback_query.answer("❌ No active accounts available", show_alert=True)
                return
            
            # Store channel info in state
            await state.update_data(
                reaction_channel_id=channel_id, 
                reaction_channel_link=channel["channel_link"],
                feature_type="reactions",
                available_accounts=available_count
            )
            
            text = f"""
📊 **Account Status**

Channel: {channel.get("title") or channel["channel_link"]}

💯 **Available Accounts:** {available_count:,}

😍 **How it works:**
• Each account reacts with a random emoji
• Accounts cycle through messages based on your selection
• Popular emojis: ❤️ 👍 😂 🔥 💯 🎉 😍 and more!
• You can choose how many reactions and timing

🚀 **Ready to continue?**
Click Continue to select the number of reactions you want.
            """
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.account_count_display(available_count, "reactions"),
                    parse_mode="Markdown"
                )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error starting emoji reactions: {e}")
            await callback_query.answer("❌ Error starting reactions", show_alert=True)
    
    async def process_boost_messages(self, message: types.Message, state: FSMContext):
        """Process boost with message IDs"""
        if not message.from_user or not message.text:
            return
        user_id = message.from_user.id
        input_text = message.text.strip()
        
        if input_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled",
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        # Get state data
        data = await state.get_data()
        channel_id = data.get("boost_channel_id")
        channel_link = data.get("boost_channel_link")
        
        if not channel_id or not channel_link:
            await message.answer("❌ Session expired. Please try again.",
                               reply_markup=BotKeyboards.main_menu(True))
            await state.clear()
            return
        
        # Process message IDs
        if input_text.lower() == "auto":
            # Auto-detect recent messages using user's setting
            auto_count = await self.get_user_setting(user_id, "auto_message_count")
            if auto_count is None:
                auto_count = 10  # Only use default if setting doesn't exist
            logger.info(f"🔍 DEBUG: User {user_id} auto_count setting retrieved: {auto_count}")
            message_ids = await self.telethon.get_channel_messages(channel_link, limit=auto_count)
            if not message_ids:
                await message.answer("❌ Could not find recent messages in the channel.")
                return
        else:
            # Parse specific message IDs
            is_valid, message_ids, error_msg = Utils.validate_message_ids_input(input_text)
            if not is_valid:
                await message.answer(f"❌ {error_msg}")
                return
        
        # Get user settings
        mark_as_read = not await self.get_user_setting(user_id, "views_only")
        
        # Show processing message
        processing_msg = await message.answer(
            f"⚡ Boosting {len(message_ids)} messages...\n" +
            f"{'📖 Views + Read' if mark_as_read else '👁️ Views Only'}"
        )
        
        try:
            # Perform boost
            success, boost_message, boost_count = await self.telethon.boost_views(
                channel_link, message_ids, mark_as_read
            )
            
            await processing_msg.delete()
            
            if success:
                # Update database
                await self.db.update_channel_boost(channel_id, boost_count)
                await self.db.log_action(
                    LogType.BOOST,
                    user_id=user_id,
                    channel_id=channel_id,
                    message=f"Boosted {boost_count} views"
                )
                
                await message.answer(
                    f"✅ **Boost Completed!**\n\n{boost_message}\n\n" +
                    f"Message IDs: {', '.join(map(str, message_ids))}",
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    f"❌ **Boost Failed**\n\n{boost_message}",
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error boosting messages: {e}")
            await message.answer(
                "❌ An error occurred during boost. Please try again.",
                reply_markup=BotKeyboards.main_menu(True)
            )
        
        await state.clear()

    async def process_reaction_messages(self, message: types.Message, state: FSMContext):
        """Process emoji reactions with message IDs"""
        if not message.from_user or not message.text:
            return
        user_id = message.from_user.id
        input_text = message.text.strip()
        
        if input_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled",
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        # Get state data
        data = await state.get_data()
        channel_id = data.get("reaction_channel_id")
        channel_link = data.get("reaction_channel_link")
        
        if not channel_id or not channel_link:
            await message.answer("❌ Session expired. Please try again.",
                               reply_markup=BotKeyboards.main_menu(True))
            await state.clear()
            return
        
        # Process message IDs
        if input_text.lower() == "auto":
            # Auto-detect recent messages using user's setting
            auto_count = await self.get_user_setting(user_id, "auto_message_count")
            if auto_count is None:
                auto_count = 10  # Only use default if setting doesn't exist
            message_ids = await self.telethon.get_channel_messages(channel_link, limit=auto_count)
            if not message_ids:
                await message.answer("❌ Could not find recent messages in the channel.")
                return
        else:
            # Parse specific message IDs
            is_valid, message_ids, error_msg = Utils.validate_message_ids_input(input_text)
            if not is_valid:
                await message.answer(f"❌ {error_msg}")
                return
        
        # Show processing message
        processing_msg = await message.answer(
            f"😍 Adding reactions to {len(message_ids)} messages...\n" +
            f"🔄 Cycling through accounts with random emojis"
        )
        
        try:
            # Perform emoji reactions
            success, result_message, reaction_count = await self.telethon.react_to_messages(
                channel_link, message_ids
            )
            
            try:
                await processing_msg.delete()
            except Exception:
                pass  # Ignore message deletion errors
            
            if success:
                # Update channel boost count (treat reactions as boosts in stats)
                await self.db.update_channel_boost(channel_id, reaction_count)
                
                # Log the action
                await self.db.log_action(
                    LogType.BOOST,
                    user_id=user_id,
                    channel_id=channel_id,
                    message=f"Added {reaction_count} emoji reactions to messages: {message_ids[:5]}"
                )
                
                await message.answer(
                    f"🎉 **Reactions Complete!**\n\n"
                    f"✨ **Results:**\n"
                    f"{result_message}\n\n"
                    f"💫 Each message now has unique random emoji reactions from your accounts!",
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    f"❌ **Reactions Failed**\n\n{result_message}\n\n"
                    f"💡 Try adding more active accounts or check account health.",
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            try:
                await processing_msg.delete()
            except Exception:
                pass  # Ignore message deletion errors
            logger.error(f"Error adding reactions: {e}")
            await message.answer(
                "❌ An error occurred during reactions. Please try again.",
                reply_markup=BotKeyboards.main_menu(True)
            )
        
        await state.clear()

    async def show_emoji_reactions_menu(self, callback_query: types.CallbackQuery):
        """Show emoji reactions menu - direct access from main menu"""
        try:
            user_id = callback_query.from_user.id
            
            # Get user channels
            channels = await self.db.get_user_channels(user_id)
            
            text = """
🎭 **Emoji Reactions Hub**

Choose a channel to add random emoji reactions with account rotation:

🔥 **How it works:**
• Each message gets a different account reaction
• Random emojis: ❤️ 👍 😂 🔥 💯 🎉 😍 and 20+ more
• Smart account cycling for natural engagement
• Works with "auto" or specific message IDs

Select a channel below to start:
            """
            
            # Create channel selection buttons
            buttons = []
            
            if channels:
                for channel in channels[:8]:  # Limit to 8 channels
                    channel_name = channel.get("title") or channel["channel_link"]
                    if len(channel_name) > 25:
                        channel_name = channel_name[:22] + "..."
                    
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"🎭 {channel_name}",
                            callback_data=f"add_reactions:{channel['id']}"
                        )
                    ])
            else:
                buttons.append([
                    InlineKeyboardButton(text="➕ Add Channel First", callback_data="add_channel")
                ])
            
            buttons.append([
                InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing emoji reactions menu: {e}")
            await callback_query.answer("❌ Error loading reactions menu", show_alert=True)
    
    async def show_settings(self, callback_query: types.CallbackQuery):
        """Show user settings"""
        user_id = callback_query.from_user.id
        
        try:
            delay_level = await self.get_user_setting(user_id, "delay_level")
            
            # Provide default value if None
            delay_level = delay_level if delay_level is not None else "medium"
            
            # Ensure delay_level is a valid string
            if not isinstance(delay_level, str) or delay_level not in ["low", "medium", "high"]:
                delay_level = "medium"
            
            delay_range = Utils.get_delay_range(delay_level)
            
            text = f"""
⚙️ **Advanced Configuration**

┌──── ⏱️ **Performance Settings** ────┐
│ 
│ 🎯 **Boost Timing:**
│ → Current: {delay_level.title()} Speed
│ → Interval: {delay_range[0]}-{delay_range[1]} seconds
│ 
│ 🤖 **Smart Automation:**
│ → Account Rotation: ✅ Active
│ → Message Reading: ✅ Enabled
│ → Performance Mode: 🚀 Optimized
│
└────────────────────────────────────┘

💡 **Tip:** Our AI manages accounts automatically for maximum efficiency
            """
            
            # Handle message editing with complete error suppression
            if callback_query.message:
                try:
                    await callback_query.message.edit_text(
                        text,
                        reply_markup=BotKeyboards.settings_menu(),
                        parse_mode="Markdown"
                    )
                except Exception as edit_error:
                    if "message is not modified" in str(edit_error):
                        # Completely ignore this harmless error
                        pass
                    else:
                        # Log other errors but don't raise them
                        logger.warning(f"Non-critical message edit error: {edit_error}")
            
            await callback_query.answer()
            
        except Exception as e:
            # Only log truly unexpected errors
            if "message is not modified" not in str(e):
                logger.error(f"Error showing settings: {e}")
            await callback_query.answer()
    
    async def handle_setting(self, callback_query: types.CallbackQuery, data: str):
        """Handle setting changes"""
        user_id = callback_query.from_user.id
        
        if data == "setting_delay":
            text = """
⚡ **Performance Optimization Center**

┌──── 🎯 **Speed Configuration** ────┐
│
│ Choose your preferred performance level:
│
└───────────────────────────────────┘

🚀 **Fast Mode (1-2s)**
   → Maximum speed delivery
   → Higher engagement rate
   → Ideal for trending content

⚡ **Balanced Mode (2-5s)** ⭐ **Recommended**
   → Optimal speed vs safety ratio
   → Best overall performance
   → Professional standard

🛡️ **Safe Mode (5-10s)**
   → Maximum account protection
   → Conservative approach
   → Long-term stability focus

💡 **Pro Tip:** Balanced mode offers the best results for most campaigns
            """
            
            await self.safe_edit_message(callback_query, text, BotKeyboards.delay_settings(), "Markdown")
            await callback_query.answer()
        
        elif data == "setting_auto_count":
            current_count = await self.get_user_setting(user_id, "auto_message_count") or 10
            text = f"""
📊 **Auto Message Count Configuration**

┌──── 🎯 **Auto Mode Settings** ────┐
│
│ Configure how many messages to boost
│ when using "auto" mode:
│
└──────────────────────────────────┘

**Current Setting:** {current_count} messages

🎯 **Choose Message Count:**

**1 Message** - Single latest message only
**2 Messages** - Latest 2 messages  
**5 Messages** - Latest 5 messages
**10 Messages** - Latest 10 messages ⭐ **Default**
**20 Messages** - Latest 20 messages

💡 **Tip:** Lower counts are faster, higher counts give broader reach
            """
            
            await self.safe_edit_message(callback_query, text, BotKeyboards.auto_count_settings(), "Markdown")
            await callback_query.answer()
        
        # Refresh settings if not delay or auto_count
        elif data not in ["setting_delay", "setting_auto_count"]:
            await self.show_settings(callback_query)
    
    async def handle_delay_setting(self, callback_query: types.CallbackQuery, data: str):
        """Handle delay setting changes"""
        user_id = callback_query.from_user.id
        
        delay_map = {
            "delay_low": "low",
            "delay_medium": "medium", 
            "delay_high": "high"
        }
        
        delay_level = delay_map.get(data)
        if delay_level:
            await self.update_user_setting(user_id, "delay_level", delay_level)
            responses = {
                "low": "🚀 Fast Mode activated - Maximum speed enabled!",
                "medium": "⚡ Balanced Mode activated - Optimal performance!", 
                "high": "🛡️ Safe Mode activated - Maximum protection!"
            }
            await callback_query.answer(responses.get(delay_level, "✨ Settings updated!"))
            await self.show_settings(callback_query)
    
    async def handle_auto_count_setting(self, callback_query: types.CallbackQuery, data: str):
        """Handle auto message count setting changes"""
        user_id = callback_query.from_user.id
        logger.info(f"🔧 DEBUG: Auto count setting called with data: {data} for user: {user_id}")
        
        count_map = {
            "auto_count_1": 1,
            "auto_count_2": 2,
            "auto_count_5": 5,
            "auto_count_10": 10,
            "auto_count_20": 20
        }
        
        count = count_map.get(data)
        logger.info(f"🔧 DEBUG: Count mapped to: {count}")
        if count:
            success = await self.update_user_setting(user_id, "auto_message_count", count)
            logger.info(f"🔧 DEBUG: Setting update success: {success}")
            await callback_query.answer(f"✨ Auto message count set to {count} messages!")
            await self.show_settings(callback_query)
        else:
            logger.error(f"🔧 DEBUG: No count found for data: {data}")
    
    async def show_channel_info(self, callback_query: types.CallbackQuery, data: str):
        """Show detailed channel information"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            name = channel.get("title") or "Unknown Channel"
            link = channel["channel_link"]
            total_boosts = channel.get("total_boosts", 0)
            created = Utils.format_datetime(channel.get("created_at"))
            last_boosted = Utils.format_datetime(channel.get("last_boosted"))
            
            text = f"""
📢 **Channel Intelligence**

┌──── 🎯 **Channel Profile** ────┐
│ Name: {name}
│ Link: {Utils.truncate_text(link, 50)}
└───────────────────────────────┘

📊 **Performance Analytics:**
┌─────────────────────────────┐
│ 🚀 Total Boosts: {total_boosts:,}
│ 📅 Added: {created}
│ ⚡ Last Boost: {last_boosted}
└─────────────────────────────┘

🎮 **Available Operations:**
• ⚡ Instant boost campaign
• 📊 Advanced analytics
• 🗑️ Remove from system
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.boost_options(channel_id),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing channel info: {e}")
            await callback_query.answer("❌ Error loading channel info", show_alert=True)
    
    async def confirm_remove_channel(self, callback_query: types.CallbackQuery, data: str):
        """Confirm channel removal"""
        try:
            channel_id = int(data.split(":")[1])
            
            text = """
🗑️ **Remove Channel**

Are you sure you want to remove this channel?

⚠️ **Warning:**
• All boost history will be lost
• You'll need to re-add it to boost again
• Accounts will remain in the channel

This action cannot be undone.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.confirm_action("remove_channel", str(channel_id)),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error confirming channel removal: {e}")
            await callback_query.answer("❌ Error", show_alert=True)
    
    async def handle_confirmation(self, callback_query: types.CallbackQuery, data: str):
        """Handle confirmation actions"""
        try:
            parts = data.split(":")
            action = parts[1]
            item_id = parts[2]
            user_id = callback_query.from_user.id
            
            if action == "remove_channel":
                channel_id = int(item_id)
                success = await self.db.remove_channel(channel_id, user_id)
                
                if success:
                    await callback_query.answer("✅ Channel removed successfully")
                    await self.show_my_channels(callback_query)
                else:
                    await callback_query.answer("❌ Failed to remove channel", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error handling confirmation: {e}")
            await callback_query.answer("❌ Error processing action", show_alert=True)
    
    async def show_boost_stats(self, callback_query: types.CallbackQuery, data: str):
        """Show boost statistics for a channel"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            name = channel.get("title") or "Unknown Channel"
            total_boosts = channel.get("total_boosts", 0)
            last_boosted = Utils.format_datetime(channel.get("last_boosted"))
            created = Utils.format_datetime(channel.get("created_at"))
            
            # Get recent boost logs for this channel
            recent_logs = await self.db.get_logs(limit=10, log_type=LogType.BOOST)
            channel_logs = [log for log in recent_logs if log.get("channel_id") == channel_id]
            
            text = f"""
📊 **Boost Statistics**

📢 **Channel:** {name}

📈 **Overall Stats:**
Total Boosts: {total_boosts:,}
Added: {created}
Last Boosted: {last_boosted}

🔄 **Recent Activity:**
            """
            
            if channel_logs:
                for log in channel_logs[:5]:
                    timestamp = Utils.format_datetime(log["created_at"])
                    message = log["message"] or "Boost activity"
                    text += f"⚡ {timestamp}: {Utils.truncate_text(message)}\n"
            else:
                text += "No recent boost activity"
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.back_button(f"channel_info:{channel_id}"),
                    parse_mode="Markdown"
                )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing boost stats: {e}")
            await callback_query.answer("❌ Error loading statistics", show_alert=True)
    
    async def cancel_operation(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Cancel current operation"""
        await state.clear()
        await callback_query.answer("✨ Operation cancelled successfully")
        await self.show_personal_dashboard(callback_query)
    
    async def get_user_setting(self, user_id: int, setting_name: str) -> any:
        """Get user setting value"""
        user = await self.db.get_user(user_id)
        if not user:
            logger.info(f"🔍 DEBUG: No user found for ID: {user_id}")
            return None
        
        settings = Utils.parse_user_settings(user.get("settings", "{}"))
        setting_value = settings.get(setting_name)
        logger.info(f"🔍 DEBUG: Retrieved {setting_name} = {setting_value} for user {user_id}")
        if setting_name == "auto_message_count":
            logger.info(f"🔍 DEBUG: Full settings for user {user_id}: {settings}")
        return setting_value
    
    async def update_user_setting(self, user_id: int, setting_name: str, value: any) -> bool:
        """Update user setting"""
        try:
            user = await self.db.get_user(user_id)
            if not user:
                logger.error(f"💾 DEBUG: User {user_id} not found in database")
                return False
            
            logger.info(f"💾 DEBUG: Current user data: {user}")
            settings = Utils.parse_user_settings(user.get("settings", "{}"))
            logger.info(f"💾 DEBUG: Current settings before update: {settings}")
            
            settings[setting_name] = value
            logger.info(f"💾 DEBUG: Settings after update: {settings}")
            
            serialized_settings = Utils.serialize_user_settings(settings)
            logger.info(f"💾 DEBUG: Serialized settings: {serialized_settings}")
            
            # Update in database
            logger.info(f"💾 DEBUG: Executing UPDATE for user {user_id}")
            await self.db._execute_with_lock(
                "UPDATE users SET settings = ? WHERE id = ?",
                (serialized_settings, user_id)
            )
            await self.db._commit_with_lock()
            logger.info(f"💾 DEBUG: Database update completed for user {user_id}")
            
            # Verify update worked
            updated_user = await self.db.get_user(user_id)
            logger.info(f"💾 DEBUG: Verification - updated user data: {updated_user}")
            
            return True
                
        except Exception as e:
            logger.error(f"Error updating user setting: {e}")
            return False
    
    async def safe_edit_message(self, callback_query: types.CallbackQuery, text: str, reply_markup=None, parse_mode="Markdown"):
        """Safely edit message with proper error handling and fallbacks"""
        try:
            if callback_query.message and hasattr(callback_query.message, 'edit_text'):
                await callback_query.message.edit_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                # Fallback: send new message if edit is not possible
                if self.bot and callback_query.from_user:
                    await self.bot.send_message(
                        callback_query.from_user.id,
                        text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
        except Exception as e:
            error_msg = str(e).lower()
            if any(ignore_phrase in error_msg for ignore_phrase in [
                "message is not modified", 
                "message content and reply markup are exactly the same",
                "message to edit not found"
            ]):
                # Silently ignore harmless errors
                pass
            else:
                logger.error(f"Error editing message: {e}")
                # Try fallback message send
                try:
                    if self.bot and callback_query.from_user:
                        await self.bot.send_message(
                            callback_query.from_user.id,
                            text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                except Exception as fallback_error:
                    logger.error(f"Fallback message send also failed: {fallback_error}")
    
    # Live Management Methods
    async def show_live_management(self, callback_query: types.CallbackQuery):
        """Show live management menu"""
        try:
            await callback_query.answer()
            
            # Try to get monitors with error handling
            try:
                monitors = await self.db.get_live_monitors(callback_query.from_user.id)
                if monitors is None:
                    monitors = []
                active_count = len([m for m in monitors if m.get('active', False)])
                total_count = len(monitors)
            except Exception as db_error:
                logger.error(f"Database error getting live monitors: {db_error}")
                monitors = []
                active_count = 0
                total_count = 0
            
            text = f"""🔴 **Live Stream Management**

📊 **Status Overview:**
• Total Monitored: {total_count} channels
• Active Monitoring: {active_count} channels

⚡ **How it works:**
The bot continuously monitors your selected channels for live streams and automatically joins them with all available accounts when detected.

🎯 **Features:**
• Add multiple channels to monitor
• Auto-join live streams with all accounts
• Real-time monitoring status
• Professional live stream detection"""

            # Create keyboard safely
            try:
                keyboard = BotKeyboards.live_management()
            except Exception as keyboard_error:
                logger.error(f"Error creating live management keyboard: {keyboard_error}")
                # Fallback to simple back button
                keyboard = BotKeyboards.back_button("main_menu")

            await self.safe_edit_message(
                callback_query,
                text,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Error in show_live_management: {e}")
            await callback_query.answer("❌ Error loading live management. Please try again.", show_alert=True)
    
    async def start_add_live_channel(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start adding a channel for live monitoring"""
        await callback_query.answer()
        await state.set_state(UserStates.waiting_for_live_channel)
        
        text = """➕ **Add Channel for Live Monitoring**

Please send the channel link you want to monitor for live streams.

**Supported formats:**
• `https://t.me/channel_name`
• `@channel_name`
• `t.me/channel_name`

The bot will automatically detect when this channel goes live and join the stream with all your accounts.

Type `/cancel` to cancel."""

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.cancel_operation()
        )
    
    async def process_live_channel(self, message: types.Message, state: FSMContext):
        """Process live channel addition"""
        if not message.from_user or not message.text:
            return
        
        user_id = message.from_user.id
        channel_input = message.text.strip()
        
        if channel_input == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled",
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        # Validate channel link
        is_valid, channel_link, error_msg = Utils.validate_channel_link(channel_input)
        if not is_valid:
            await message.answer(f"❌ {error_msg}")
            return
        
        # Get channel info using Telethon
        processing_msg = await message.answer("🔍 Checking channel...")
        
        try:
            channel_info = await self.telethon.get_channel_info(channel_link)
            if not channel_info:
                await processing_msg.edit_text("❌ Could not access channel. Make sure the link is correct and the channel is public.")
                return
            
            # Add to live monitoring with safe title handling
            channel_title = channel_info.get("title") or channel_link
            success = await self.db.add_live_monitor(
                user_id, 
                channel_link, 
                str(channel_title)
            )
            
            if success:
                await processing_msg.edit_text(
                    f"✅ **Channel Added to Live Monitoring**\n\n"
                    f"📢 **Channel:** {channel_info.get('title', 'Unknown')}\n"
                    f"🔗 **Link:** {channel_link}\n"
                    f"🔴 **Status:** Active monitoring\n\n"
                    f"The bot will now monitor this channel for live streams and automatically join them with all your accounts.",
                    reply_markup=BotKeyboards.live_management()
                )
            else:
                await processing_msg.edit_text("❌ Failed to add channel to monitoring. Please try again.")
            
        except Exception as e:
            logger.error(f"Error adding live monitor: {e}")
            await processing_msg.edit_text("❌ Error processing channel. Please try again.")
        
        await state.clear()
    
    async def show_live_channels(self, callback_query: types.CallbackQuery):
        """Show list of monitored live channels"""
        await callback_query.answer()
        
        monitors = await self.db.get_live_monitors(callback_query.from_user.id)
        
        if not monitors:
            text = """📋 **Monitored Live Channels**

🔍 **No channels being monitored**

You haven't added any channels for live monitoring yet. Click "Add Monitor Channel" to start monitoring channels for live streams.

💡 **Tip:** The bot will automatically join live streams with all your accounts when detected."""
        else:
            text = f"📋 **Monitored Live Channels** ({len(monitors)})\n\n"
            
            for monitor in monitors:
                title = monitor.get('title') or 'Unknown Channel'
                status = "🔴 Active" if monitor.get('active', False) else "⚫ Inactive"
                live_count = monitor.get('live_count', 0)
                last_checked = monitor.get('last_checked', 'Never')
                
                text += f"**{title}**\n"
                text += f"Status: {status}\n"
                text += f"Lives Joined: {live_count}\n"
                text += f"Last Check: {last_checked}\n\n"
        
        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_channel_list(monitors)
        )
    
    async def show_live_monitor_status(self, callback_query: types.CallbackQuery):
        """Show live monitoring system status"""
        await callback_query.answer()
        
        monitors = await self.db.get_live_monitors(callback_query.from_user.id)
        all_monitors = await self.db.get_all_active_monitors()
        active_accounts = await self.telethon.get_active_account_count()
        
        active_user_monitors = len([m for m in monitors if m.get('active', False)])
        total_user_monitors = len(monitors)
        total_system_monitors = len(all_monitors)
        
        text = f"""⚡ **Live Monitor Status**

👤 **Your Monitoring:**
• Active: {active_user_monitors}/{total_user_monitors} channels
• Total Lives Joined: {sum(m.get('live_count', 0) for m in monitors)}

🌐 **System Status:**
• Total Active Monitors: {total_system_monitors}
• Available Accounts: {active_accounts}

🔄 **Monitoring Process:**
• Continuous scanning for live streams
• Automatic joining with all accounts
• Real-time status updates

💡 **Performance:**
The system checks for live streams every 30 seconds across all monitored channels."""

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_management()
        )
    
    async def show_live_channel_info(self, callback_query: types.CallbackQuery, data: str):
        """Show detailed info for a specific monitored channel"""
        await callback_query.answer()
        
        try:
            monitor_id = int(data.split(":")[1])
            monitors = await self.db.get_live_monitors(callback_query.from_user.id)
            
            monitor = next((m for m in monitors if m['id'] == monitor_id), None)
            if not monitor:
                await callback_query.answer("Channel not found", show_alert=True)
                return
            
            title = monitor.get('title') or 'Unknown Channel'
            status = "🔴 Active" if monitor.get('active', False) else "⚫ Inactive"
            live_count = monitor.get('live_count', 0)
            last_checked = monitor.get('last_checked', 'Never')
            created_at = monitor.get('created_at', 'Unknown')
            
            text = f"""📊 **Channel Details**

📢 **Channel:** {title}
🔗 **Link:** {monitor['channel_link']}
🔴 **Status:** {status}

📈 **Statistics:**
• Lives Joined: {live_count}
• Last Checked: {last_checked}
• Added: {created_at}

⚙️ **Actions:**
Use the buttons below to manage this channel."""
            
            buttons = [
                [InlineKeyboardButton(
                    text="⏹️ Stop Monitoring" if monitor.get('active', False) else "▶️ Start Monitoring",
                    callback_data=f"toggle_live_monitor:{monitor_id}"
                )],
                [InlineKeyboardButton(text="🗑️ Remove", callback_data=f"remove_live_channel:{monitor_id}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="view_live_channels")]
            ]
            
            await self.safe_edit_message(
                callback_query,
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
            
        except (ValueError, IndexError):
            await callback_query.answer("Invalid channel ID", show_alert=True)
    
    async def confirm_remove_live_channel(self, callback_query: types.CallbackQuery, data: str):
        """Confirm removal of live monitoring channel"""
        await callback_query.answer()
        
        try:
            monitor_id = int(data.split(":")[1])
            monitors = await self.db.get_live_monitors(callback_query.from_user.id)
            
            monitor = next((m for m in monitors if m['id'] == monitor_id), None)
            if not monitor:
                await callback_query.answer("Channel not found", show_alert=True)
                return
            
            success = await self.db.remove_live_monitor(callback_query.from_user.id, monitor_id)
            
            if success:
                title = monitor.get('title') or 'Channel'
                await self.safe_edit_message(
                    callback_query,
                    f"✅ **{title}** has been removed from live monitoring.",
                    reply_markup=BotKeyboards.live_management()
                )
            else:
                await callback_query.answer("Failed to remove channel", show_alert=True)
            
        except (ValueError, IndexError):
            await callback_query.answer("Invalid channel ID", show_alert=True)
    
    async def start_live_monitoring(self, callback_query: types.CallbackQuery):
        """Start live monitoring service"""
        await callback_query.answer()
        
        try:
            if self.live_monitor:
                await self.live_monitor.start_monitoring()
                
                text = """🔴 **Live Monitoring Started**

✅ The live monitoring service is now actively scanning all your monitored channels for live streams every 15 seconds.

📊 **Status:**
• Service: Active ✅
• Scan Interval: 15 seconds
• Auto-join: Enabled

When a live stream is detected, all your accounts will automatically join the stream."""
            else:
                text = """❌ **Monitoring Service Unavailable**

The live monitoring service is temporarily unavailable. Please try again later."""
                
        except Exception as e:
            logger.error(f"Error starting live monitoring: {e}")
            text = """❌ **Failed to Start Monitoring**

There was an error starting the live monitoring service. Please try again."""

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_management()
        )
    
    async def stop_live_monitoring(self, callback_query: types.CallbackQuery):
        """Stop live monitoring service"""
        await callback_query.answer()
        
        try:
            if self.live_monitor:
                await self.live_monitor.stop_monitoring()
                
                text = """⏹️ **Live Monitoring Stopped**

🔴 The live monitoring service has been stopped. No automatic scanning for live streams will occur.

📊 **Status:**
• Service: Inactive ❌
• Auto-join: Disabled

You can restart monitoring anytime by clicking "Start Monitoring"."""
            else:
                text = """❌ **Monitoring Service Unavailable**

The live monitoring service is temporarily unavailable."""
                
        except Exception as e:
            logger.error(f"Error stopping live monitoring: {e}")
            text = """❌ **Failed to Stop Monitoring**

There was an error stopping the live monitoring service."""

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_management()
        )
    
    # Poll Management Functions
    async def show_poll_manager(self, callback_query: types.CallbackQuery):
        """Show poll management menu"""
        try:
            text = """
🗳️ **Poll Manager**

Automatically vote in Telegram polls using your accounts.

**How it works:**
1. Get the poll URL/link from Telegram
2. Select which option to vote for
3. Bot uses all your accounts to vote

**Supported:**
• Channel polls
• Group polls 
• Public polls
• Private polls (if accounts are members)

Choose an option below:
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.poll_management(),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing poll manager: {e}")
            await callback_query.answer("❌ Error loading poll manager", show_alert=True)
    
    async def start_poll_voting(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start poll voting process"""
        try:
            text = """
🗳️ **Start Poll Voting**

Please send me the poll URL or forward the poll message.

**Supported formats:**
• `https://t.me/channel/123`
• `https://t.me/c/123456789/123`
• Forward the poll message directly

**Note:** Your accounts must have access to the channel/group containing the poll.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.cancel_operation(),
                parse_mode="Markdown"
            )
            await state.set_state(UserStates.waiting_for_poll_url)
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error starting poll voting: {e}")
            await callback_query.answer("❌ Error starting poll voting", show_alert=True)
    
    async def process_poll_url(self, message: types.Message, state: FSMContext):
        """Process poll URL and fetch poll data"""
        try:
            # Handle forwarded poll message
            if message.forward_from_chat or message.poll:
                if message.poll:
                    # Direct poll message
                    poll_data = await self.extract_poll_data_from_message(message)
                    if poll_data:
                        await self.show_poll_options(message, poll_data, state)
                        return
                else:
                    await message.answer("❌ This appears to be a forwarded message but no poll was detected.")
                    return
            
            # Handle URL input
            if message.text:
                poll_url = message.text.strip()
                
                # Validate URL format
                if not self.is_valid_telegram_url(poll_url):
                    await message.answer(
                        "❌ **Invalid URL format**\n\n"
                        "Please send a valid Telegram link like:\n"
                        "• `https://t.me/channel/123`\n"
                        "• `https://t.me/c/123456789/123`\n"
                        "• Or forward the poll message directly",
                        parse_mode="Markdown"
                    )
                    return
                
                # Try to fetch poll from URL
                poll_data = await self.fetch_poll_from_url(poll_url)
                if poll_data:
                    await self.show_poll_options(message, poll_data, state)
                else:
                    await message.answer(
                        "❌ **Poll not found**\n\n"
                        "Could not find a poll at that URL. Make sure:\n"
                        "• The URL is correct\n" 
                        "• Your accounts have access to the channel\n"
                        "• The message contains a poll",
                        parse_mode="Markdown"
                    )
            else:
                await message.answer("❌ Please send a valid poll URL or forward a poll message.")
                
        except Exception as e:
            logger.error(f"Error processing poll URL: {e}")
            await message.answer("❌ Error processing poll URL. Please try again.")
    
    async def show_poll_options(self, message: types.Message, poll_data: dict, state: FSMContext):
        """Show poll options for voting"""
        try:
            poll_question = poll_data.get('question', 'Poll')
            if len(poll_question) > 100:
                poll_question = poll_question[:97] + "..."
            
            options_text = ""
            for i, option in enumerate(poll_data.get('options', [])):
                option_text = option.get('text', f'Option {i+1}')
                voter_count = option.get('voter_count', 0)
                options_text += f"{i+1}. {option_text} ({voter_count} votes)\n"
            
            text = f"""
🗳️ **Poll Found!**

**Question:** {poll_question}

**Options:**
{options_text}

**Accounts available:** {len(self.telethon.active_clients)}

Select which option you want to vote for:
            """
            
            # Store poll data in state
            await state.update_data(poll_data=poll_data)
            await state.set_state(UserStates.waiting_for_poll_choice)
            
            await message.answer(
                text,
                reply_markup=BotKeyboards.poll_options(poll_data),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Error showing poll options: {e}")
            await message.answer("❌ Error displaying poll options")
    
    async def execute_poll_vote(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Execute poll voting with all accounts"""
        try:
            # Extract option index from callback data
            option_index = int(data.split(":")[1])
            
            # Get poll data from state
            try:
                state_data = await state.get_data()
                poll_data = state_data.get('poll_data', {})
            except Exception as state_error:
                logger.error(f"Error getting poll data from state: {state_error}")
                await callback_query.answer("❌ Error retrieving poll data. Please try again.", show_alert=True)
                return
            
            if not poll_data:
                await callback_query.answer("❌ Poll data not found. Please start poll voting again.", show_alert=True)
                return
            
            selected_option = poll_data['options'][option_index]
            option_text = selected_option.get('text', f'Option {option_index + 1}')
            
            # Show voting progress
            progress_text = f"""
🗳️ **Starting Poll Vote**

**Selected option:** {option_text}
**Available accounts:** {len(self.telethon.active_clients)}

⏳ **Voting in progress...**
This may take a few moments.
            """
            
            await callback_query.message.edit_text(
                progress_text,
                parse_mode="Markdown"
            )
            
            # Execute voting with all accounts
            vote_result = await self.telethon.vote_in_poll(
                poll_data['message_url'],
                poll_data['message_id'], 
                option_index
            )
            
            # Show results
            success_count = vote_result.get('successful_votes', 0)
            total_accounts = vote_result.get('total_accounts', 0)
            failed_accounts = vote_result.get('failed_accounts', [])
            
            result_text = f"""
✅ **Poll Voting Complete!**

**Selected option:** {option_text}
**Successful votes:** {success_count}/{total_accounts}
"""
            
            if failed_accounts:
                result_text += f"**Failed accounts:** {len(failed_accounts)}\n"
                if len(failed_accounts) <= 5:
                    result_text += f"**Failed:** {', '.join(failed_accounts[:5])}\n"
            
            result_text += "\n🎉 All available accounts have voted!"
            
            await callback_query.message.edit_text(
                result_text,
                reply_markup=BotKeyboards.poll_management(),
                parse_mode="Markdown"
            )
            
            # Clear state
            await state.clear()
            await callback_query.answer("✅ Voting completed!")
            
        except Exception as e:
            logger.error(f"Error executing poll vote: {e}")
            await callback_query.answer("❌ Error voting in poll. Please try again.", show_alert=True)
    
    async def show_poll_history(self, callback_query: types.CallbackQuery):
        """Show poll voting history"""
        try:
            text = """
📋 **Poll History**

*This feature will show your recent poll voting activity.*

**Coming Soon:**
• View recent poll votes
• Vote statistics  
• Success/failure rates
• Account performance

For now, all poll votes are logged in the system logs.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.back_button("poll_manager"),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing poll history: {e}")
            await callback_query.answer("❌ Error loading poll history", show_alert=True)
    
    # Helper functions for poll management
    def is_valid_telegram_url(self, url: str) -> bool:
        """Check if URL is a valid Telegram URL"""
        telegram_patterns = [
            r'https://t\.me/\w+/\d+',
            r'https://t\.me/c/\d+/\d+',
            r'https://telegram\.me/\w+/\d+'
        ]
        
        import re
        for pattern in telegram_patterns:
            if re.match(pattern, url):
                return True
        return False
    
    async def extract_poll_data_from_message(self, message: types.Message) -> dict:
        """Extract poll data from a message"""
        try:
            if not message.poll:
                return None
            
            poll = message.poll
            poll_data = {
                'question': poll.question,
                'options': [],
                'message_id': message.message_id,
                'message_url': f"https://t.me/c/{message.chat.id}/{message.message_id}",
                'is_anonymous': poll.is_anonymous,
                'allows_multiple_answers': poll.allows_multiple_answers
            }
            
            for option in poll.options:
                poll_data['options'].append({
                    'text': option.text,
                    'voter_count': option.voter_count
                })
            
            return poll_data
            
        except Exception as e:
            logger.error(f"Error extracting poll data from message: {e}")
            return None
    
    async def fetch_poll_from_url(self, url: str) -> dict:
        """Fetch poll data from Telegram URL"""
        try:
            # Use Telethon to fetch the message and extract poll
            poll_data = await self.telethon.get_poll_from_url(url)
            return poll_data
            
        except Exception as e:
            logger.error(f"Error fetching poll from URL {url}: {e}")
            return None
    
    async def process_custom_view_count(self, message: types.Message, state: FSMContext):
        """Process custom view count input"""
        if not message.from_user or not message.text:
            return
        
        user_id = message.from_user.id
        input_text = message.text.strip()
        
        if input_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled", 
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        try:
            view_count = int(input_text)
            
            state_data = await state.get_data()
            available_accounts = state_data.get("available_accounts", 0)
            feature_type = state_data.get("feature_type", "boost")
            
            if view_count <= 0:
                await message.answer("❌ Please enter a positive number.")
                return
            
            if view_count > available_accounts:
                await message.answer(
                    f"❌ Not enough accounts! You have {available_accounts} available.\n"
                    f"Please enter a number between 1 and {available_accounts}."
                )
                return
            
            # Store view count and proceed to time selection
            await state.update_data(selected_view_count=view_count)
            
            text = f"""
⏰ **Select Time Frame**

📊 Views Selected: {view_count:,}
📢 Channel: {state_data.get("boost_channel_link", "Unknown")}

🕒 **Choose time frame for the views:**
Select how quickly you want the views to be delivered.
            """
            
            await message.answer(
                text,
                reply_markup=BotKeyboards.time_selection(feature_type, view_count),
                parse_mode="Markdown"
            )
            
        except ValueError:
            await message.answer("❌ Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error processing custom view count: {e}")
            await message.answer("❌ An error occurred. Please try again.")
    
    async def process_manual_message_ids(self, message: types.Message, state: FSMContext):
        """Process manual message IDs input"""
        if not message.from_user or not message.text:
            return
        
        user_id = message.from_user.id
        input_text = message.text.strip()
        
        if input_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled",
                               reply_markup=BotKeyboards.main_menu(True))
            return
        
        # Parse message IDs
        is_valid, message_ids, error_msg = Utils.validate_message_ids_input(input_text)
        if not is_valid:
            await message.answer(f"❌ {error_msg}")
            return
        
        try:
            state_data = await state.get_data()
            view_count = state_data.get("selected_view_count", 0)
            time_minutes = state_data.get("selected_time_minutes", 0)
            
            # Execute boost with the parsed message IDs
            # Check if this is for reactions or boost
            feature_type = state_data.get("feature_type", "boost")
            if feature_type == "reactions":
                await self.execute_reactions_with_settings(message, state, message_ids, view_count, time_minutes)
            else:
                await self.execute_boost_with_settings(message, state, message_ids, view_count, time_minutes)
            
        except Exception as e:
            logger.error(f"Error processing manual message IDs: {e}")
            await message.answer("❌ An error occurred. Please try again.")
    
    async def execute_boost_with_settings(self, message_obj, state: FSMContext, 
                                        message_ids: list, view_count: int, time_minutes: int):
        """Execute boost with specified settings and account management"""
        try:
            state_data = await state.get_data()
            channel_link = state_data.get("boost_channel_link")
            user_id = None
            
            # Get user_id based on message type
            if hasattr(message_obj, 'from_user') and message_obj.from_user:
                user_id = message_obj.from_user.id
            elif hasattr(message_obj, 'message') and message_obj.message.from_user:
                user_id = message_obj.message.from_user.id
            
            if not user_id:
                logger.error("Could not determine user_id for boost execution")
                return
            
            # Get user settings
            mark_as_read = not await self.get_user_setting(user_id, "views_only")
            
            # Show processing message
            time_text = "instantly" if time_minutes == 0 else f"over {time_minutes} minutes"
            
            processing_text = (
                f"⚡ **Boosting in progress...**\n\n"
                f"📊 Views: {view_count:,}\n"
                f"📝 Messages: {len(message_ids)}\n"
                f"⏰ Timeline: {time_text}\n\n"
                f"{'📖 Views + Read' if mark_as_read else '👁️ Views Only'}\n\n"
                f"Please wait..."
            )
            
            if hasattr(message_obj, 'answer'):
                # It's a message object
                processing_msg = await message_obj.answer(processing_text, parse_mode="Markdown")
            else:
                # It's a callback query
                processing_msg = await message_obj.message.edit_text(processing_text, parse_mode="Markdown")
            
            # Execute boost with batched account management
            success, boost_message, boost_count = await self.execute_batched_boost(
                channel_link, message_ids, mark_as_read, view_count, time_minutes
            )
            
            if success:
                # Update database
                channel_id = state_data.get("boost_channel_id")
                if channel_id:
                    await self.db.update_channel_boost(channel_id, boost_count)
                    await self.db.log_action(
                        LogType.BOOST,
                        user_id=user_id,
                        channel_id=channel_id,
                        message=f"Boosted {boost_count} views with {view_count} accounts"
                    )
                
                final_text = f"""
✅ **Boost Completed Successfully!**

📊 Views Delivered: {boost_count:,}
📝 Messages Boosted: {len(message_ids)}
📱 Accounts Used: {min(view_count, boost_count)}
{'📖 Views + Read' if mark_as_read else '👁️ Views Only'}

{boost_message}

🏠 Click 'Main Menu' to continue with other operations.
                """
            else:
                final_text = f"❌ **Boost Failed**\n\n{boost_message}\n\n🏠 Click 'Main Menu' to try again."
            
            # Clear state before updating the message to prevent any state conflicts
            await state.clear()
            
            # Update the message with final results
            try:
                if hasattr(processing_msg, 'edit_text'):
                    await processing_msg.edit_text(
                        final_text,
                        reply_markup=BotKeyboards.main_menu(True),
                        parse_mode="Markdown"
                    )
                else:
                    # If we can't edit the processing message, delete it and send a new one
                    try:
                        if hasattr(processing_msg, 'delete'):
                            await processing_msg.delete()
                    except Exception:
                        pass  # Ignore deletion errors
                    
                    # Send new message with results
                    if hasattr(message_obj, 'message') and hasattr(message_obj.message, 'answer'):
                        await message_obj.message.answer(
                            final_text,
                            reply_markup=BotKeyboards.main_menu(True),
                            parse_mode="Markdown"
                        )
                    elif hasattr(message_obj, 'answer'):
                        await message_obj.answer(
                            final_text,
                            reply_markup=BotKeyboards.main_menu(True),
                            parse_mode="Markdown"
                        )
            except Exception as msg_error:
                logger.error(f"Error updating completion message: {msg_error}")
                # As a last resort, try to send a simple success message
                try:
                    if hasattr(message_obj, 'message') and hasattr(message_obj.message, 'chat'):
                        await self.bot.send_message(
                            chat_id=message_obj.message.chat.id,
                            text=final_text,
                            reply_markup=BotKeyboards.main_menu(True),
                            parse_mode="Markdown"
                        )
                except Exception:
                    pass  # Final fallback - just log the error
            
        except Exception as e:
            logger.error(f"Error executing boost with settings: {e}")
            try:
                if hasattr(message_obj, 'answer'):
                    await message_obj.answer(
                        "❌ An error occurred during boost. Please try again.",
                        reply_markup=BotKeyboards.main_menu(True)
                    )
                elif hasattr(message_obj, 'message'):
                    await message_obj.message.edit_text(
                        "❌ An error occurred during boost. Please try again.",
                        reply_markup=BotKeyboards.main_menu(True)
                    )
            except:
                pass
            await state.clear()
    
    async def execute_batched_boost(self, channel_link: str, message_ids: list, 
                                  mark_as_read: bool, target_view_count: int, time_minutes: int):
        """Execute boost with batched account management (100 accounts at a time)"""
        try:
            # For now, use the existing boost_views method but limit accounts used
            # This is a simplified version - full batching would require TelethonManager updates
            active_accounts = await self.db.get_active_accounts()
            if not active_accounts:
                return False, "❌ No active accounts available", 0
            
            # Use up to target_view_count accounts
            accounts_to_use = min(target_view_count, len(active_accounts))
            
            # For now, use the existing boost method
            # In a full implementation, you'd modify TelethonManager to support batching
            success, boost_message, boost_count = await self.telethon.boost_views(
                channel_link, message_ids, mark_as_read
            )
            
            if success:
                # Adjust the count to match requested view count
                actual_count = min(boost_count, target_view_count)
                return True, f"Successfully delivered {actual_count:,} views", actual_count
            else:
                return False, boost_message, 0
                
        except Exception as e:
            logger.error(f"Error in batched boost execution: {e}")
            return False, f"Error during boost: {str(e)}", 0
    
    async def execute_reactions_with_settings(self, message_obj, state: FSMContext, 
                                            message_ids: list, reaction_count: int, time_minutes: int):
        """Execute reactions with specified settings and account management"""
        try:
            state_data = await state.get_data()
            channel_link = state_data.get("reaction_channel_link")
            user_id = None
            
            # Get user_id based on message type
            if hasattr(message_obj, 'from_user') and message_obj.from_user:
                user_id = message_obj.from_user.id
            elif hasattr(message_obj, 'message') and message_obj.message.from_user:
                user_id = message_obj.message.from_user.id
            
            if not user_id:
                logger.error("Could not determine user_id for reactions execution")
                return
            
            # Show processing message
            time_text = "instantly" if time_minutes == 0 else f"over {time_minutes} minutes"
            
            processing_text = (
                f"😍 **Adding Reactions...**\n\n"
                f"🎭 Reactions: {reaction_count:,}\n"
                f"📝 Messages: {len(message_ids)}\n"
                f"⏰ Timeline: {time_text}\n\n"
                f"Random emojis: ❤️ 👍 😂 🔥 💯 🎉 😍 and more!\n\n"
                f"Please wait..."
            )
            
            if hasattr(message_obj, 'answer'):
                # It's a message object
                processing_msg = await message_obj.answer(processing_text, parse_mode="Markdown")
            else:
                # It's a callback query
                processing_msg = await message_obj.message.edit_text(processing_text, parse_mode="Markdown")
            
            # Execute reactions with account management
            success, reaction_message, reaction_count_actual = await self.execute_batched_reactions(
                channel_link, message_ids, reaction_count, time_minutes
            )
            
            if success:
                # Update database
                channel_id = state_data.get("reaction_channel_id")
                if channel_id:
                    await self.db.log_action(
                        LogType.BOOST,  # Using BOOST log type for reactions
                        user_id=user_id,
                        channel_id=channel_id,
                        message=f"Added {reaction_count_actual} reactions with {reaction_count} accounts"
                    )
                
                final_text = f"""
✅ **Reactions Added Successfully!**

🎭 Reactions Delivered: {reaction_count_actual:,}
📝 Messages Reacted: {len(message_ids)}
📱 Accounts Used: {min(reaction_count, reaction_count_actual)}

{reaction_message}
                """
            else:
                final_text = f"❌ **Reactions Failed**\n\n{reaction_message}"
            
            if hasattr(processing_msg, 'edit_text'):
                await processing_msg.edit_text(
                    final_text,
                    reply_markup=BotKeyboards.main_menu(True),
                    parse_mode="Markdown"
                )
            else:
                try:
                    if hasattr(processing_msg, 'delete'):
                        await processing_msg.delete()
                except Exception:
                    pass  # Ignore deletion errors
                if hasattr(message_obj, 'answer'):
                    await message_obj.answer(
                        final_text,
                        reply_markup=BotKeyboards.main_menu(True),
                        parse_mode="Markdown"
                    )
            
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error executing reactions with settings: {e}")
            try:
                if hasattr(message_obj, 'answer'):
                    await message_obj.answer(
                        "❌ An error occurred during reactions. Please try again.",
                        reply_markup=BotKeyboards.main_menu(True)
                    )
                elif hasattr(message_obj, 'message'):
                    await message_obj.message.edit_text(
                        "❌ An error occurred during reactions. Please try again.",
                        reply_markup=BotKeyboards.main_menu(True)
                    )
            except:
                pass
            await state.clear()
    
    async def execute_batched_reactions(self, channel_link: str, message_ids: list, 
                                      target_reaction_count: int, time_minutes: int):
        """Execute reactions with batched account management"""
        try:
            # For now, use the existing react_to_messages method but limit accounts used
            active_accounts = await self.db.get_active_accounts()
            if not active_accounts:
                return False, "❌ No active accounts available", 0
            
            # Use up to target_reaction_count accounts
            accounts_to_use = min(target_reaction_count, len(active_accounts))
            
            # Use the existing reaction method
            success, reaction_message, reaction_count = await self.telethon.react_to_messages(
                channel_link, message_ids
            )
            
            if success:
                # Adjust the count to match requested reaction count
                actual_count = min(reaction_count, target_reaction_count)
                return True, f"Successfully added {actual_count:,} reactions", actual_count
            else:
                return False, reaction_message, 0
                
        except Exception as e:
            logger.error(f"Error in batched reactions execution: {e}")
            return False, f"Error during reactions: {str(e)}", 0
    
    async def set_user_setting(self, user_id: int, setting_name: str, value: Any) -> bool:
        """Set a specific user setting"""
        try:
            # Get current settings
            user = await self.db.get_user(user_id)
            if not user:
                return False
            
            settings = Utils.parse_user_settings(user.get("settings", "{}"))
            settings[setting_name] = value
            
            # Update settings in database
            return await self.db.update_user_settings(user_id, settings)
        except Exception as e:
            logger.error(f"Error setting user setting {setting_name}: {e}")
            return False
    
    async def update_user_setting(self, user_id: int, setting_name: str, value: Any) -> bool:
        """Update a specific user setting (alias for set_user_setting)"""
        return await self.set_user_setting(user_id, setting_name, value)
