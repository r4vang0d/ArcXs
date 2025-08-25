"""
Inline keyboard definitions for the Telegram bot
Creates beautiful and modern UI elements
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any

class BotKeyboards:
    """Static class for keyboard generation"""
    
    @staticmethod
    def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
        """Main menu keyboard based on user role"""
        buttons = []
        
        if is_admin:
            buttons = [
                [InlineKeyboardButton(text="👥 User Panel", callback_data="user_panel")],
                [InlineKeyboardButton(text="🔧 Admin Panel", callback_data="admin_panel")],
            ]
        else:
            buttons = [
                [InlineKeyboardButton(text="➕ Add Channel", callback_data="add_channel")],
                [InlineKeyboardButton(text="📊 My Stats", callback_data="my_stats")],
                [InlineKeyboardButton(text="⚡ Boost Views", callback_data="boost_views")],
                [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
            ]
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def user_panel() -> InlineKeyboardMarkup:
        """User panel keyboard"""
        buttons = [
            [InlineKeyboardButton(text="➕ Add Channel", callback_data="add_channel")],
            [InlineKeyboardButton(text="📋 My Channels", callback_data="my_channels")],
            [InlineKeyboardButton(text="📊 My Stats", callback_data="my_stats")],
            [InlineKeyboardButton(text="⚡ Boost Views", callback_data="boost_views")],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def admin_panel() -> InlineKeyboardMarkup:
        """Admin panel keyboard"""
        buttons = [
            [InlineKeyboardButton(text="📱 Manage Accounts", callback_data="admin_accounts")],
            [InlineKeyboardButton(text="📊 System Logs", callback_data="admin_logs")],
            [InlineKeyboardButton(text="❌ Failed Operations", callback_data="admin_failed")],
            [InlineKeyboardButton(text="🚫 Banned Accounts", callback_data="admin_banned")],
            [InlineKeyboardButton(text="⚡ Account Health", callback_data="admin_health")],
            [InlineKeyboardButton(text="👥 User Stats", callback_data="admin_users")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def account_management() -> InlineKeyboardMarkup:
        """Account management keyboard"""
        buttons = [
            [InlineKeyboardButton(text="➕ Add Account", callback_data="add_account")],
            [InlineKeyboardButton(text="📋 List Accounts", callback_data="list_accounts")],
            [InlineKeyboardButton(text="🗑️ Remove Account", callback_data="remove_account")],
            [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_accounts")],
            [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def channel_list(channels: List[Dict[str, Any]], user_id: int) -> InlineKeyboardMarkup:
        """Generate keyboard for channel list"""
        buttons = []
        
        for i, channel in enumerate(channels):
            channel_name = channel.get("title") or channel["channel_link"]
            if len(channel_name) > 30:
                channel_name = channel_name[:27] + "..."
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"📢 {channel_name}",
                    callback_data=f"channel_info:{channel['id']}"
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=f"remove_channel:{channel['id']}"
                )
            ])
        
        if not channels:
            buttons.append([
                InlineKeyboardButton(text="➕ Add Your First Channel", callback_data="add_channel")
            ])
        
        buttons.append([InlineKeyboardButton(text="🔙 User Panel", callback_data="user_panel")])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def boost_options(channel_id: int) -> InlineKeyboardMarkup:
        """Boost options for a specific channel"""
        buttons = [
            [InlineKeyboardButton(text="⚡ Instant Boost", callback_data=f"instant_boost:{channel_id}")],
            [InlineKeyboardButton(text="🕐 Schedule Boost", callback_data=f"schedule_boost:{channel_id}")],
            [InlineKeyboardButton(text="📊 Boost Stats", callback_data=f"boost_stats:{channel_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="boost_views")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Settings configuration menu"""
        buttons = [
            [InlineKeyboardButton(text="👁️ Views Only", callback_data="setting_views_only")],
            [InlineKeyboardButton(text="👁️📖 Views + Read", callback_data="setting_views_read")],
            [InlineKeyboardButton(text="🔄 Account Rotation", callback_data="setting_rotation")],
            [InlineKeyboardButton(text="⏱️ Boost Delay", callback_data="setting_delay")],
            [InlineKeyboardButton(text="🔙 User Panel", callback_data="user_panel")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def delay_settings() -> InlineKeyboardMarkup:
        """Delay configuration options"""
        buttons = [
            [InlineKeyboardButton(text="🐇 Low (1-2s)", callback_data="delay_low")],
            [InlineKeyboardButton(text="🚶 Medium (2-5s)", callback_data="delay_medium")],
            [InlineKeyboardButton(text="🐢 High (5-10s)", callback_data="delay_high")],
            [InlineKeyboardButton(text="🔙 Settings", callback_data="settings")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def confirm_action(action: str, data: str) -> InlineKeyboardMarkup:
        """Confirmation keyboard for dangerous actions"""
        buttons = [
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm:{action}:{data}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_action")
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def account_list_admin(accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """Admin account list with status indicators"""
        buttons = []
        
        for account in accounts[:10]:  # Limit to 10 accounts per page
            status_emoji = {
                "active": "✅",
                "banned": "🚫",
                "floodwait": "⏳",
                "inactive": "❌"
            }
            
            emoji = status_emoji.get(account["status"], "❓")
            phone = account["phone"]
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {phone}",
                    callback_data=f"account_details:{account['id']}"
                )
            ])
        
        if not accounts:
            buttons.append([
                InlineKeyboardButton(text="➕ Add First Account", callback_data="add_account")
            ])
        
        buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="refresh_accounts"),
            InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def back_button(callback_data: str) -> InlineKeyboardMarkup:
        """Simple back button"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data=callback_data)]
        ])
    
    @staticmethod
    def cancel_operation() -> InlineKeyboardMarkup:
        """Cancel current operation"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_operation")]
        ])
    
    @staticmethod
    def log_types() -> InlineKeyboardMarkup:
        """Log filtering options"""
        buttons = [
            [InlineKeyboardButton(text="📥 All Logs", callback_data="logs_all")],
            [InlineKeyboardButton(text="🔗 Joins", callback_data="logs_join")],
            [InlineKeyboardButton(text="⚡ Boosts", callback_data="logs_boost")],
            [InlineKeyboardButton(text="❌ Errors", callback_data="logs_error")],
            [InlineKeyboardButton(text="🚫 Bans", callback_data="logs_ban")],
            [InlineKeyboardButton(text="⏳ Flood Waits", callback_data="logs_flood_wait")],
            [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
