"""
User handlers for the Telegram View Booster Bot
Handles channel management, boosting, and settings
"""
import asyncio
import json
import logging
from typing import Optional

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

class UserHandler:
    """Handles user-specific operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, telethon_manager: TelethonManager):
        self.config = config
        self.db = db_manager
        self.telethon = telethon_manager
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
            await self.execute_poll_vote(callback_query, data)
        elif data.startswith("channel_info:"):
            await self.show_channel_info(callback_query, data)
        elif data.startswith("remove_channel:"):
            await self.confirm_remove_channel(callback_query, data)
        elif data.startswith("instant_boost:"):
            await self.start_instant_boost(callback_query, data, state)
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
        """Start instant boost process"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            # Get channel info
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            # Store channel info in state
            await state.update_data(boost_channel_id=channel_id, boost_channel_link=channel["channel_link"])
            
            auto_count = await self.get_user_setting(user_id, "auto_message_count") or 10
            text = f"""
⚡ **Instant Boost**

Channel: {channel.get("title") or channel["channel_link"]}

**Option 1: Auto-detect messages**
Send "auto" to boost the latest {auto_count} messages automatically.

**Option 2: Specific messages**
Send message IDs or message links separated by commas or spaces.
Examples:
• 123, 124, 125
• 100 101 102
• 50-55 (range)
• https://t.me/channel/123
• https://t.me/c/1234567890/456

**Current Settings:**
Views + Read: {'✅' if not await self.get_user_setting(user_id, 'views_only') else '❌'}
Account Rotation: {'✅' if await self.get_user_setting(user_id, 'account_rotation') else '❌'}
Auto Count: {auto_count} messages

Send message IDs/links or "auto", or /cancel to abort.
            """
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.cancel_operation(),
                    parse_mode="Markdown"
                )
            await state.set_state(UserStates.waiting_for_message_ids)
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error starting instant boost: {e}")
            await callback_query.answer("❌ Error starting boost", show_alert=True)

    async def start_add_reactions(self, callback_query: types.CallbackQuery, data: str, state: FSMContext):
        """Start emoji reactions process"""
        try:
            channel_id = int(data.split(":")[1])
            user_id = callback_query.from_user.id
            
            # Get channel info
            channels = await self.db.get_user_channels(user_id)
            channel = next((ch for ch in channels if ch["id"] == channel_id), None)
            
            if not channel:
                await callback_query.answer("❌ Channel not found", show_alert=True)
                return
            
            # Store channel info in state
            await state.update_data(reaction_channel_id=channel_id, reaction_channel_link=channel["channel_link"])
            
            text = f"""
😍 **Add Emoji Reactions**

Channel: {channel.get("title") or channel["channel_link"]}

**How it works:**
• Each account reacts with a random emoji 
• Accounts cycle through message IDs one by one
• Popular emojis: ❤️ 👍 😂 🔥 💯 🎉 😍 and more!

**Option 1: Auto-detect messages**
Send "auto" to react to the latest 10 messages automatically.

**Option 2: Specific messages**
Send message IDs separated by commas or spaces.
Examples:
• 123, 124, 125
• 100 101 102
• 50-55 (range)

Send message IDs or "auto", or /cancel to abort.
            """
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.cancel_operation(),
                    parse_mode="Markdown"
                )
            await state.set_state(UserStates.waiting_for_reaction_message_ids)
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
        """Safely edit message with proper error handling"""
        if not callback_query.message:
            return
        
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            if "message is not modified" in str(e):
                # Silently ignore this harmless error
                pass
            else:
                logger.error(f"Error editing message: {e}")
                raise e
    
    # Live Management Methods
    async def show_live_management(self, callback_query: types.CallbackQuery):
        """Show live management menu"""
        await callback_query.answer()
        
        monitors = await self.db.get_live_monitors(callback_query.from_user.id)
        active_count = len([m for m in monitors if m.get('active', False)])
        total_count = len(monitors)
        
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

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_management()
        )
    
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
            
            # Add to live monitoring
            success = await self.db.add_live_monitor(
                user_id, 
                channel_link, 
                channel_info.get("title")
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
        
        text = """🔴 **Live Monitoring Started**

✅ The live monitoring service is now actively scanning all your monitored channels for live streams every 30 seconds.

📊 **Status:**
• Service: Active
• Scan Interval: 30 seconds
• Auto-join: Enabled

When a live stream is detected, all your accounts will automatically join the stream."""

        await self.safe_edit_message(
            callback_query,
            text,
            reply_markup=BotKeyboards.live_management()
        )
    
    async def stop_live_monitoring(self, callback_query: types.CallbackQuery):
        """Stop live monitoring service"""
        await callback_query.answer()
        
        text = """⏹️ **Live Monitoring Stopped**

🔴 The live monitoring service has been paused. No automatic scanning for live streams will occur.

📊 **Status:**
• Service: Inactive
• Auto-join: Disabled

You can restart monitoring anytime by clicking "Start Monitoring"."""

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
    
    async def execute_poll_vote(self, callback_query: types.CallbackQuery, data: str):
        """Execute poll voting with all accounts"""
        try:
            # Extract option index from callback data
            option_index = int(data.split(":")[1])
            
            # Get poll data from state
            from aiogram.fsm.context import FSMContext
            from aiogram.dispatcher.event.context import Context
            
            context = Context()
            state = FSMContext(
                storage=callback_query.bot.dispatcher.storage,  
                key=callback_query.bot.dispatcher.storage.build_key(
                    chat=callback_query.message.chat.id,
                    user=callback_query.from_user.id
                )
            )
            state_data = await state.get_data()
            poll_data = state_data.get('poll_data', {})
            
            if not poll_data:
                await callback_query.answer("❌ Poll data not found. Please try again.", show_alert=True)
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
