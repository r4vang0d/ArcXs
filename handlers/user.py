"""
User handlers for the Telegram View Booster Bot
Handles channel management, boosting, and settings
"""
import asyncio
import json
import logging
from typing import Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import Config
from database import DatabaseManager, LogType
from telethon_manager import TelethonManager
from keyboards import BotKeyboards
from utils import Utils

logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_message_ids = State()

class UserHandler:
    """Handles user-specific operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, telethon_manager: TelethonManager):
        self.config = config
        self.db = db_manager
        self.telethon = telethon_manager
    
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
            await self.show_user_panel(callback_query)
        elif data == "add_channel":
            await self.start_add_channel(callback_query, state)
        elif data == "my_channels":
            await self.show_my_channels(callback_query)
        elif data == "my_stats":
            await self.show_my_stats(callback_query)
        elif data == "boost_views":
            await self.show_boost_menu(callback_query)
        elif data == "settings":
            await self.show_settings(callback_query)
        elif data.startswith("channel_info:"):
            await self.show_channel_info(callback_query, data)
        elif data.startswith("remove_channel:"):
            await self.confirm_remove_channel(callback_query, data)
        elif data.startswith("instant_boost:"):
            await self.start_instant_boost(callback_query, data, state)
        elif data.startswith("boost_stats:"):
            await self.show_boost_stats(callback_query, data)
        elif data.startswith("setting_"):
            await self.handle_setting(callback_query, data)
        elif data.startswith("delay_"):
            await self.handle_delay_setting(callback_query, data)
        elif data.startswith("confirm:"):
            await self.handle_confirmation(callback_query, data)
        elif data == "cancel_action" or data == "cancel_operation":
            await self.cancel_operation(callback_query, state)
        else:
            await callback_query.answer("Unknown command")
    
    async def handle_message(self, message: types.Message, state: FSMContext):
        """Handle user text messages"""
        current_state = await state.get_state()
        
        if current_state == UserStates.waiting_for_channel.state:
            await self.process_add_channel(message, state)
        elif current_state == UserStates.waiting_for_message_ids.state:
            await self.process_boost_messages(message, state)
    
    async def show_main_menu(self, callback_query: types.CallbackQuery):
        """Show main menu"""
        user_id = callback_query.from_user.id
        is_admin = self.config.is_admin(user_id)
        
        welcome_text = f"""
🚀 **View Booster Bot**

Welcome back, {callback_query.from_user.first_name}!

{'Choose your panel:' if is_admin else 'What would you like to do?'}
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                welcome_text,
                reply_markup=BotKeyboards.main_menu(is_admin),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def show_user_panel(self, callback_query: types.CallbackQuery):
        """Show user panel"""
        user_id = callback_query.from_user.id
        
        # Get user stats
        channels = await self.db.get_user_channels(user_id)
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        is_premium = await self.db.is_premium_user(user_id)
        
        panel_text = f"""
👤 **User Panel**

📊 **Your Account:**
Status: {'Premium ⭐' if is_premium else 'Free 🆓'}
Channels: {len(channels)}/{('∞' if is_premium else '1')}
Total Boosts: {total_boosts:,}

What would you like to do?
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                panel_text,
                reply_markup=BotKeyboards.user_panel(),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def start_add_channel(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start add channel process"""
        user_id = callback_query.from_user.id
        
        # Check limits for free users
        is_premium = await self.db.is_premium_user(user_id)
        if not is_premium:
            channels = await self.db.get_user_channels(user_id)
            if len(channels) >= 1:
                await callback_query.answer(
                    "❌ Free users can only add 1 channel. Upgrade to Premium for unlimited channels!",
                    show_alert=True
                )
                return
        
        text = """
➕ **Add Channel**

Send the channel link or username:

📱 **Supported formats:**
• https://t.me/channel_name
• https://t.me/joinchat/invite_code
• @channel_name
• channel_name

⚠️ **Note:**
• All system accounts will automatically join this channel
• Both public and private channels are supported
• Make sure the channel allows new members

Send the channel link or /cancel to abort.
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.cancel_operation(),
                parse_mode="Markdown"
            )
        await state.set_state(UserStates.waiting_for_channel)
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
                               reply_markup=BotKeyboards.user_panel())
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
                        reply_markup=BotKeyboards.user_panel(),
                        parse_mode="Markdown"
                    )
                else:
                    await processing_msg.delete()
                    await message.answer(
                        "⚠️ Channel joined but failed to save to database. Please try again.",
                        reply_markup=BotKeyboards.user_panel()
                    )
            else:
                await processing_msg.delete()
                await message.answer(
                    f"❌ **Failed to Add Channel**\n\n{join_message}\n\n" +
                    "Please check the channel link and try again.",
                    reply_markup=BotKeyboards.user_panel(),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error adding channel: {e}")
            await message.answer(
                "❌ An error occurred while adding the channel. Please try again.",
                reply_markup=BotKeyboards.user_panel()
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
                last_boosted = Utils.format_datetime(channel.get("last_boosted"))
                
                text += f"📢 **{name}**\n"
                text += f"   ⚡ Boosts: {boosts}\n"
                text += f"   📅 Last: {last_boosted}\n\n"
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.channel_list(channels, user_id),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def show_my_stats(self, callback_query: types.CallbackQuery):
        """Show user statistics"""
        user_id = callback_query.from_user.id
        channels = await self.db.get_user_channels(user_id)
        is_premium = await self.db.is_premium_user(user_id)
        
        total_boosts = sum(channel.get("total_boosts", 0) for channel in channels)
        
        # Get recent boost logs for this user
        recent_logs = await self.db.get_logs(limit=5, log_type=LogType.BOOST)
        user_recent_logs = [log for log in recent_logs if log["user_id"] == user_id]
        
        stats_text = f"""
📊 **My Statistics**

👤 **Account Info:**
Status: {'Premium ⭐' if is_premium else 'Free 🆓'}
Member Since: {Utils.format_datetime(None)}

📢 **Channel Stats:**
Total Channels: {len(channels)}
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
                reply_markup=BotKeyboards.back_button("user_panel"),
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
        
        buttons.append([types.InlineKeyboardButton(text="🔙 User Panel", callback_data="user_panel")])
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
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
            
            text = f"""
⚡ **Instant Boost**

Channel: {channel.get("title") or channel["channel_link"]}

**Option 1: Auto-detect messages**
Send "auto" to boost the latest 10 messages automatically.

**Option 2: Specific messages**
Send message IDs separated by commas or spaces.
Examples:
• 123, 124, 125
• 100 101 102
• 50-55 (range)

**Current Settings:**
Views + Read: {'✅' if not await self.get_user_setting(user_id, 'views_only') else '❌'}
Account Rotation: {'✅' if await self.get_user_setting(user_id, 'account_rotation') else '❌'}

Send message IDs or "auto", or /cancel to abort.
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
    
    async def process_boost_messages(self, message: types.Message, state: FSMContext):
        """Process boost with message IDs"""
        if not message.from_user or not message.text:
            return
        user_id = message.from_user.id
        input_text = message.text.strip()
        
        if input_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled",
                               reply_markup=BotKeyboards.user_panel())
            return
        
        # Get state data
        data = await state.get_data()
        channel_id = data.get("boost_channel_id")
        channel_link = data.get("boost_channel_link")
        
        if not channel_id or not channel_link:
            await message.answer("❌ Session expired. Please try again.",
                               reply_markup=BotKeyboards.user_panel())
            await state.clear()
            return
        
        # Process message IDs
        if input_text.lower() == "auto":
            # Auto-detect recent messages
            message_ids = await self.telethon.get_channel_messages(channel_link, limit=10)
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
                    reply_markup=BotKeyboards.user_panel(),
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    f"❌ **Boost Failed**\n\n{boost_message}",
                    reply_markup=BotKeyboards.user_panel(),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error boosting messages: {e}")
            await message.answer(
                "❌ An error occurred during boost. Please try again.",
                reply_markup=BotKeyboards.user_panel()
            )
        
        await state.clear()
    
    async def show_settings(self, callback_query: types.CallbackQuery):
        """Show user settings"""
        user_id = callback_query.from_user.id
        
        views_only = await self.get_user_setting(user_id, "views_only")
        rotation = await self.get_user_setting(user_id, "account_rotation")
        delay_level = await self.get_user_setting(user_id, "delay_level")
        
        text = f"""
⚙️ **Settings**

📖 **Boost Mode:**
Currently: {'👁️ Views Only' if views_only else '👁️📖 Views + Read'}

🔄 **Account Rotation:**
Currently: {'✅ Enabled' if rotation else '❌ Disabled'}

⏱️ **Boost Delay:**
Currently: {delay_level.title()} ({dict(Utils.get_delay_range(delay_level))[0]}-{dict(Utils.get_delay_range(delay_level))[1]}s)

Choose a setting to modify:
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.settings_menu(),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def handle_setting(self, callback_query: types.CallbackQuery, data: str):
        """Handle setting changes"""
        user_id = callback_query.from_user.id
        
        if data == "setting_views_only":
            await self.update_user_setting(user_id, "views_only", True)
            await callback_query.answer("✅ Set to Views Only mode")
        elif data == "setting_views_read":
            await self.update_user_setting(user_id, "views_only", False)
            await callback_query.answer("✅ Set to Views + Read mode")
        elif data == "setting_rotation":
            current = await self.get_user_setting(user_id, "account_rotation")
            await self.update_user_setting(user_id, "account_rotation", not current)
            await callback_query.answer(f"✅ Account rotation {'disabled' if current else 'enabled'}")
        elif data == "setting_delay":
            text = """
⏱️ **Boost Delay Settings**

Choose delay between account operations:

🐇 **Low (1-2s)**: Fast boosting, higher chance of flood wait
🚶 **Medium (2-5s)**: Balanced speed and safety (recommended)  
🐢 **High (5-10s)**: Slower but safer, less chance of limits

Current setting will be highlighted.
            """
            
            if callback_query.message:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=BotKeyboards.delay_settings(),
                    parse_mode="Markdown"
                )
            await callback_query.answer()
        
        # Refresh settings if not delay
        if data != "setting_delay":
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
            await callback_query.answer(f"✅ Delay set to {delay_level}")
            await self.show_settings(callback_query)
    
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
📢 **Channel Info**

**Name:** {name}
**Link:** {Utils.truncate_text(link, 50)}

📊 **Statistics:**
Total Boosts: {total_boosts:,}
Added: {created}
Last Boosted: {last_boosted}

**Available Actions:**
• Instant boost this channel
• View boost statistics
• Remove channel
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
        await callback_query.answer("❌ Operation cancelled")
        await self.show_user_panel(callback_query)
    
    async def get_user_setting(self, user_id: int, setting_name: str) -> any:
        """Get user setting value"""
        user = await self.db.get_user(user_id)
        if not user:
            return None
        
        settings = Utils.parse_user_settings(user.get("settings", "{}"))
        return settings.get(setting_name)
    
    async def update_user_setting(self, user_id: int, setting_name: str, value: any) -> bool:
        """Update user setting"""
        try:
            user = await self.db.get_user(user_id)
            if not user:
                return False
            
            settings = Utils.parse_user_settings(user.get("settings", "{}"))
            settings[setting_name] = value
            
            # Update in database
            await self.db._execute_with_lock(
                "UPDATE users SET settings = ? WHERE id = ?",
                (Utils.serialize_user_settings(settings), user_id)
            )
            await self.db._commit_with_lock()
            return True
                
        except Exception as e:
            logger.error(f"Error updating user setting: {e}")
            return False
