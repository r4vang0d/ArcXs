"""
Admin handlers for the Telegram View Booster Bot
Handles account management, logs, and system monitoring
"""
import asyncio
import logging
from datetime import datetime
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

class AdminStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_remove_phone = State()
    waiting_for_api_choice = State()
    waiting_for_custom_api_id = State()
    waiting_for_custom_api_hash = State()
    waiting_for_verification_code = State()

class AdminHandler:
    """Handles admin-specific operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, telethon_manager: TelethonManager):
        self.config = config
        self.db = db_manager
        self.telethon = telethon_manager
    
    async def handle_callback(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle admin callback queries"""
        if not callback_query.from_user or not callback_query.data:
            await callback_query.answer("Invalid request", show_alert=True)
            return
        
        data = callback_query.data
        
        if data == "admin_panel":
            await self.show_admin_panel(callback_query)
        elif data == "admin_accounts":
            await self.show_account_management(callback_query)
        elif data == "admin_logs":
            await self.show_logs_menu(callback_query)
        elif data == "admin_failed":
            await self.show_failed_operations(callback_query)
        elif data == "admin_banned":
            await self.show_banned_accounts(callback_query)
        elif data == "admin_health":
            await self.show_account_health(callback_query)
        elif data == "admin_users":
            await self.show_user_stats(callback_query)
        elif data == "add_account":
            await self.start_add_account(callback_query, state)
        elif data == "remove_account":
            await self.start_remove_account(callback_query, state)
        elif data == "list_accounts":
            await self.list_accounts(callback_query)
        elif data == "refresh_accounts":
            await self.refresh_account_status(callback_query)
        elif data == "api_default":
            await self.use_default_api(callback_query, state)
        elif data == "api_custom":
            await self.use_custom_api(callback_query, state)
        elif data == "cancel_operation":
            await self.cancel_operation(callback_query, state)
        elif data.startswith("logs_"):
            await self.show_filtered_logs(callback_query, data)
        elif data.startswith("account_details:"):
            await self.show_account_details(callback_query, data)
        else:
            await callback_query.answer("Unknown command")
    
    async def handle_message(self, message: types.Message, state: FSMContext):
        """Handle admin text messages"""
        current_state = await state.get_state()
        
        if current_state == AdminStates.waiting_for_phone.state:
            await self.process_add_account(message, state)
        elif current_state == AdminStates.waiting_for_remove_phone.state:
            await self.process_remove_account(message, state)
        elif current_state == AdminStates.waiting_for_custom_api_id.state:
            await self.process_custom_api_id(message, state)
        elif current_state == AdminStates.waiting_for_custom_api_hash.state:
            await self.process_custom_api_hash(message, state)
        elif current_state == AdminStates.waiting_for_verification_code.state:
            await self.process_verification_code(message, state)
    
    async def show_admin_panel(self, callback_query: types.CallbackQuery):
        """Show main admin panel"""
        # Get system statistics
        account_health = await self.telethon.check_account_health()
        user_count = await self.db.get_user_count()
        
        admin_text = f"""
🔧 **Admin Panel**

📊 **System Overview:**
👥 Users: {user_count}
📱 Active Accounts: {account_health.get('active', 0)}
🚫 Banned Accounts: {account_health.get('banned', 0)}
⏳ Flood Wait: {account_health.get('flood_wait', 0)}
❌ Inactive: {account_health.get('inactive', 0)}

Choose an action below:
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                admin_text,
                reply_markup=BotKeyboards.admin_panel(),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def show_account_management(self, callback_query: types.CallbackQuery):
        """Show account management options"""
        accounts = await self.db.get_accounts()
        
        text = f"""
📱 **Account Management**

Total Accounts: {len(accounts)}

Quick Actions:
• Add Account - Login with phone number
• List Accounts - View all accounts with status
• Remove Account - Delete account and session
• Refresh Status - Update account health
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.account_management(),
                parse_mode="Markdown"
            )
        await callback_query.answer()
    
    async def start_add_account(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start add account process"""
        text = f"""
➕ **Add New Account**

Choose API credentials to use:

🔹 **Default API** (Recommended)
• Quick and easy setup
• Uses system default credentials
• API ID: {self.config.DEFAULT_API_ID}

🔸 **Custom API** (Advanced)
• Use your own API credentials
• Get from https://my.telegram.org
• More control and privacy

Choose your preferred method:
        """
        
        buttons = [
            [types.InlineKeyboardButton(text="🔹 Use Default API", callback_data="api_default")],
            [types.InlineKeyboardButton(text="🔸 Use Custom API", callback_data="api_custom")],
            [types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_operation")]
        ]
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="Markdown"
            )
        await state.set_state(AdminStates.waiting_for_api_choice)
        await callback_query.answer()
    
    async def process_add_account(self, message: types.Message, state: FSMContext):
        """Process add account with phone number - start verification"""
        if not message.text:
            return
        phone = message.text.strip()
        
        if phone == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled")
            return
        
        if not Utils.is_valid_phone(phone):
            await message.answer("❌ Invalid phone number format. Please try again or /cancel")
            return
        
        formatted_phone = Utils.format_phone(phone)
        
        # Get API credentials from state
        data = await state.get_data()
        api_id = data.get("api_id", self.config.DEFAULT_API_ID)
        api_hash = data.get("api_hash", self.config.DEFAULT_API_HASH)
        
        # Show processing message
        processing_msg = await message.answer("⏳ Sending verification code... Please wait.")
        
        try:
            success, result_message, verification_data = await self.telethon.start_account_verification(formatted_phone, api_id, api_hash)
            
            await processing_msg.delete()
            
            if success:
                # Store verification data in state
                await state.update_data(verification_data=verification_data)
                
                text = f"""
✅ {result_message}

📱 **Enter Verification Code**

Please check your phone {formatted_phone} for a verification code from Telegram.

Enter the verification code you received:

📋 **Format**: 12345 (just the numbers)

⚠️ **Important:**
• Don't include spaces or dashes
• Code expires in a few minutes
• Check SMS or phone call

Send the code or /cancel to abort.
                """
                
                await message.answer(text, reply_markup=BotKeyboards.cancel_operation(), parse_mode="Markdown")
                await state.set_state(AdminStates.waiting_for_verification_code)
            else:
                await message.answer(
                    f"{result_message}\n\n❌ Failed to start verification. Please try again.",
                    reply_markup=BotKeyboards.account_management()
                )
                await state.clear()
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error starting verification: {e}")
            await message.answer(
                "❌ An error occurred while starting verification. Please try again.",
                reply_markup=BotKeyboards.account_management()
            )
            await state.clear()
    
    async def process_verification_code(self, message: types.Message, state: FSMContext):
        """Process verification code input"""
        if not message.text:
            return
        code = message.text.strip()
        
        if code == "/cancel":
            # Clean up verification data
            data = await state.get_data()
            verification_data = data.get("verification_data")
            if verification_data and verification_data.get('client'):
                try:
                    await verification_data['client'].disconnect()
                except:
                    pass
            
            await state.clear()
            await message.answer("❌ Operation cancelled", reply_markup=BotKeyboards.account_management())
            return
        
        # Validate code format
        if not code.isdigit() or len(code) < 4:
            await message.answer("❌ Invalid code format. Please enter only numbers (e.g., 12345) or /cancel")
            return
        
        # Get verification data from state
        data = await state.get_data()
        verification_data = data.get("verification_data")
        
        if not verification_data:
            await message.answer("❌ Verification session expired. Please start again.", reply_markup=BotKeyboards.account_management())
            await state.clear()
            return
        
        # Show processing message
        processing_msg = await message.answer("⏳ Verifying code... Please wait.")
        
        try:
            success, result_message = await self.telethon.complete_account_verification(verification_data, code)
            
            await processing_msg.delete()
            
            if success:
                await message.answer(
                    f"{result_message}\n\n🎉 Account successfully added and ready for use!",
                    reply_markup=BotKeyboards.account_management()
                )
            else:
                await message.answer(
                    f"{result_message}\n\nPlease try again or /cancel to abort.",
                    reply_markup=BotKeyboards.cancel_operation()
                )
                return  # Don't clear state, allow retry
        
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error completing verification: {e}")
            await message.answer(
                "❌ An error occurred during verification. Please try again or /cancel",
                reply_markup=BotKeyboards.cancel_operation()
            )
            return  # Don't clear state, allow retry
        
        await state.clear()
    
    async def use_default_api(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Use default API credentials"""
        await state.update_data(api_id=self.config.DEFAULT_API_ID, api_hash=self.config.DEFAULT_API_HASH)
        
        text = f"""
📱 **Add Account - Default API**

Using default API credentials:
• API ID: {self.config.DEFAULT_API_ID}
• API Hash: {self.config.DEFAULT_API_HASH[:8]}...

Please send the phone number for the new account.

📋 **Format examples:**
• +1234567890
• +44 123 456 7890
• 1234567890

⚠️ **Requirements:**
• Phone number has Telegram registered
• Access to SMS/calls for verification
• Two-factor authentication disabled

Send the phone number or /cancel to abort.
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.cancel_operation(),
                parse_mode="Markdown"
            )
        await state.set_state(AdminStates.waiting_for_phone)
        await callback_query.answer()
    
    async def use_custom_api(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Guide user to get custom API credentials"""
        text = """
🔸 **Custom API Setup**

📋 **Step 1: Get Your API Credentials**

1️⃣ Visit https://my.telegram.org
2️⃣ Login with your phone number
3️⃣ Go to "API Development Tools"
4️⃣ Create a new app:
   • App title: Any name (e.g., "My Bot")
   • Short name: Any short name
   • Platform: Other
   • Description: Optional

5️⃣ Copy your credentials:
   • **api_id** (number)
   • **api_hash** (32-character string)

📱 **Step 2: Send Your API ID**

Please send your **API ID** (numbers only):
Example: 12345678

Or /cancel to abort.
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.cancel_operation(),
                parse_mode="Markdown"
            )
        await state.set_state(AdminStates.waiting_for_custom_api_id)
        await callback_query.answer()
    
    async def process_custom_api_id(self, message: types.Message, state: FSMContext):
        """Process custom API ID input"""
        if not message.text:
            return
        api_id_text = message.text.strip()
        
        if api_id_text == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled", reply_markup=BotKeyboards.account_management())
            return
        
        try:
            api_id = int(api_id_text)
            await state.update_data(api_id=api_id)
            
            text = f"""
✅ **API ID Saved: {api_id}**

📱 **Step 3: Send Your API Hash**

Please send your **API Hash** (32-character string):
Example: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

⚠️ **Important:**
• API Hash is case-sensitive
• Must be exactly 32 characters
• Contains letters and numbers

Send your API Hash or /cancel to abort.
            """
            
            await message.answer(text, reply_markup=BotKeyboards.cancel_operation(), parse_mode="Markdown")
            await state.set_state(AdminStates.waiting_for_custom_api_hash)
            
        except ValueError:
            await message.answer("❌ Invalid API ID. Please send numbers only (e.g., 12345678) or /cancel")
    
    async def process_custom_api_hash(self, message: types.Message, state: FSMContext):
        """Process custom API Hash input"""
        if not message.text:
            return
        api_hash = message.text.strip()
        
        if api_hash == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled", reply_markup=BotKeyboards.account_management())
            return
        
        if len(api_hash) != 32:
            await message.answer("❌ Invalid API Hash. Must be exactly 32 characters. Please try again or /cancel")
            return
        
        data = await state.get_data()
        api_id = data.get("api_id")
        await state.update_data(api_hash=api_hash)
        
        text = f"""
✅ **Custom API Credentials Set**

• API ID: {api_id}
• API Hash: {api_hash[:8]}...

📱 **Final Step: Phone Number**

Please send the phone number for the new account.

📋 **Format examples:**
• +1234567890
• +44 123 456 7890
• 1234567890

⚠️ **Requirements:**
• Phone number has Telegram registered
• Access to SMS/calls for verification
• Two-factor authentication disabled

Send the phone number or /cancel to abort.
        """
        
        await message.answer(text, reply_markup=BotKeyboards.cancel_operation(), parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_for_phone)
    
    async def cancel_operation(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Cancel current operation"""
        await state.clear()
        await callback_query.message.edit_text(
            "❌ **Operation Cancelled**\n\nReturning to account management.",
            reply_markup=BotKeyboards.account_management(),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def start_remove_account(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start remove account process"""
        accounts = await self.db.get_accounts()
        
        if not accounts:
            await callback_query.answer("❌ No accounts to remove", show_alert=True)
            return
        
        account_list = "\n".join([
            f"📱 {account['phone']} ({account['status']})"
            for account in accounts
        ])
        
        text = f"""
🗑️ **Remove Account**

Current accounts:
{account_list}

Please send the phone number of the account to remove:

⚠️ **Warning**: This will:
• Remove the account from the system
• Delete the session file
• Stop using this account for operations

Send the phone number or /cancel to abort.
        """
        
        if callback_query.message:
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.cancel_operation(),
                parse_mode="Markdown"
            )
        await state.set_state(AdminStates.waiting_for_remove_phone)
        await callback_query.answer()
    
    async def process_remove_account(self, message: types.Message, state: FSMContext):
        """Process remove account"""
        if not message.text:
            return
        phone = message.text.strip()
        
        if phone == "/cancel":
            await state.clear()
            await message.answer("❌ Operation cancelled")
            return
        
        formatted_phone = Utils.format_phone(phone)
        
        success, result_message = await self.telethon.remove_account(formatted_phone)
        
        await message.answer(
            result_message,
            reply_markup=BotKeyboards.account_management()
        )
        await state.clear()
    
    async def list_accounts(self, callback_query: types.CallbackQuery):
        """List all accounts with status"""
        accounts = await self.db.get_accounts()
        
        if not accounts:
            text = "📱 **Account List**\n\n❌ No accounts configured yet.\n\nUse 'Add Account' to get started."
        else:
            text = f"📱 **Account List** ({len(accounts)} total)\n\n"
            
            for account in accounts:
                status_info = Utils.format_account_status(account)
                last_used = Utils.format_datetime(account.get("last_used"))
                failed_attempts = account.get("failed_attempts", 0)
                
                text += f"{status_info}\n"
                text += f"   └ Last used: {last_used}"
                if failed_attempts > 0:
                    text += f" | Failed: {failed_attempts}"
                text += "\n\n"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.account_list_admin(accounts),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def refresh_account_status(self, callback_query: types.CallbackQuery):
        """Refresh account health status"""
        await callback_query.answer("🔄 Refreshing account status...")
        
        health_stats = await self.telethon.check_account_health()
        
        text = f"""
🔄 **Account Status Refreshed**

📊 **Current Status:**
✅ Active: {health_stats.get('active', 0)}
🚫 Banned: {health_stats.get('banned', 0)}
⏳ Flood Wait: {health_stats.get('flood_wait', 0)}
❌ Inactive: {health_stats.get('inactive', 0)}

Last updated: {datetime.now().strftime('%H:%M:%S')}
        """
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.account_management(),
            parse_mode="Markdown"
        )
    
    async def show_logs_menu(self, callback_query: types.CallbackQuery):
        """Show logs filtering menu"""
        text = """
📊 **System Logs**

Choose log type to view:
• All Logs - Complete activity log
• Joins - Channel join activities
• Boosts - View boosting operations
• Errors - System errors and failures
• Bans - Account ban notifications
• Flood Waits - Rate limiting events
        """
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.log_types(),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_filtered_logs(self, callback_query: types.CallbackQuery, data: str):
        """Show filtered logs"""
        log_type_map = {
            "logs_all": None,
            "logs_join": LogType.JOIN,
            "logs_boost": LogType.BOOST,
            "logs_error": LogType.ERROR,
            "logs_ban": LogType.BAN,
            "logs_flood_wait": LogType.FLOOD_WAIT
        }
        
        log_type = log_type_map.get(data)
        logs = await self.db.get_logs(limit=20, log_type=log_type)
        
        if not logs:
            text = f"📊 **{data.replace('logs_', '').title()} Logs**\n\n❌ No logs found."
        else:
            text = f"📊 **{data.replace('logs_', '').title()} Logs** (Last 20)\n\n"
            
            for log in logs:
                timestamp = Utils.format_datetime(log["created_at"])
                message = log["message"] or "No message"
                account = f" | {log['account_phone']}" if log["account_phone"] else ""
                
                text += f"🕐 {timestamp}\n"
                text += f"📝 {message}{account}\n\n"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.back_button("admin_logs"),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_failed_operations(self, callback_query: types.CallbackQuery):
        """Show failed operations"""
        error_logs = await self.db.get_logs(limit=10, log_type=LogType.ERROR)
        
        if not error_logs:
            text = "❌ **Failed Operations**\n\n✅ No recent failures!"
        else:
            text = f"❌ **Failed Operations** (Last 10)\n\n"
            
            for log in error_logs:
                timestamp = Utils.format_datetime(log["created_at"])
                message = log["message"] or "Unknown error"
                account = log["account_phone"] or "Unknown account"
                
                text += f"🕐 {timestamp}\n"
                text += f"📱 {account}\n"
                text += f"❌ {message}\n\n"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.back_button("admin_panel"),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_banned_accounts(self, callback_query: types.CallbackQuery):
        """Show banned accounts"""
        accounts = await self.db.get_accounts()
        banned_accounts = [acc for acc in accounts if acc["status"] == "banned"]
        
        if not banned_accounts:
            text = "🚫 **Banned Accounts**\n\n✅ No banned accounts!"
        else:
            text = f"🚫 **Banned Accounts** ({len(banned_accounts)} total)\n\n"
            
            for account in banned_accounts:
                phone = account["phone"]
                banned_since = Utils.format_datetime(account.get("last_used"))
                
                text += f"📱 {phone}\n"
                text += f"   └ Banned: {banned_since}\n\n"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.back_button("admin_panel"),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_account_health(self, callback_query: types.CallbackQuery):
        """Show detailed account health"""
        health_stats = await self.telethon.check_account_health()
        accounts = await self.db.get_accounts()
        
        # Calculate additional stats
        total_accounts = len(accounts)
        health_percentage = (health_stats.get('active', 0) / total_accounts * 100) if total_accounts > 0 else 0
        
        text = f"""
⚡ **Account Health Report**

📊 **Overview:**
Total Accounts: {total_accounts}
Health Score: {health_percentage:.1f}%

📈 **Status Breakdown:**
✅ Active: {health_stats.get('active', 0)} ({health_stats.get('active', 0)/total_accounts*100:.1f}%)
🚫 Banned: {health_stats.get('banned', 0)} ({health_stats.get('banned', 0)/total_accounts*100:.1f}%)
⏳ Flood Wait: {health_stats.get('flood_wait', 0)} ({health_stats.get('flood_wait', 0)/total_accounts*100:.1f}%)
❌ Inactive: {health_stats.get('inactive', 0)} ({health_stats.get('inactive', 0)/total_accounts*100:.1f}%)

🔧 **Recommendations:**
        """
        
        if health_stats.get('banned', 0) > 0:
            text += "• Remove banned accounts\n"
        if health_stats.get('inactive', 0) > 0:
            text += "• Check inactive account sessions\n"
        if health_stats.get('active', 0) < 3:
            text += "• Add more active accounts for better rotation\n"
        if health_percentage == 100:
            text += "• All accounts are healthy! 🎉\n"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.back_button("admin_panel"),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_user_stats(self, callback_query: types.CallbackQuery):
        """Show user statistics"""
        user_count = await self.db.get_user_count()
        
        # Get recent logs to show activity
        recent_logs = await self.db.get_logs(limit=5)
        
        text = f"""
👥 **User Statistics**

📊 **Overview:**
Total Users: {user_count}

🔄 **Recent Activity:**
        """
        
        if recent_logs:
            for log in recent_logs:
                timestamp = Utils.format_datetime(log["created_at"])
                message = log["message"] or "Activity"
                text += f"🕐 {timestamp}: {Utils.truncate_text(message)}\n"
        else:
            text += "No recent activity"
        
        await callback_query.message.edit_text(
            text,
            reply_markup=BotKeyboards.back_button("admin_panel"),
            parse_mode="Markdown"
        )
        await callback_query.answer()
    
    async def show_account_details(self, callback_query: types.CallbackQuery, data: str):
        """Show detailed account information"""
        try:
            account_id = int(data.split(":")[1])
            accounts = await self.db.get_accounts()
            account = next((acc for acc in accounts if acc["id"] == account_id), None)
            
            if not account:
                await callback_query.answer("❌ Account not found", show_alert=True)
                return
            
            status_info = Utils.format_account_status(account)
            created = Utils.format_datetime(account.get("created_at"))
            last_used = Utils.format_datetime(account.get("last_used"))
            failed_attempts = account.get("failed_attempts", 0)
            
            text = f"""
📱 **Account Details**

{status_info}

📅 **Timeline:**
Created: {created}
Last Used: {last_used}

📊 **Statistics:**
Failed Attempts: {failed_attempts}

🔧 **Actions Available:**
Use the account management menu to add/remove accounts.
            """
            
            await callback_query.message.edit_text(
                text,
                reply_markup=BotKeyboards.back_button("list_accounts"),
                parse_mode="Markdown"
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error showing account details: {e}")
            await callback_query.answer("❌ Error loading account details", show_alert=True)
