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
        """Main menu keyboard - Personal use only"""
        # Always return personal interface since it's personal use
        buttons = [
            [InlineKeyboardButton(text="🎯 Add Channel", callback_data="add_channel"),
             InlineKeyboardButton(text="🚀 Boost Views", callback_data="boost_views")],
            [InlineKeyboardButton(text="🎭 Emoji Reactions", callback_data="emoji_reactions"),
             InlineKeyboardButton(text="📊 Analytics", callback_data="my_stats")],
            [InlineKeyboardButton(text="📱 Manage Accounts", callback_data="admin_accounts"),
             InlineKeyboardButton(text="💚 System Health", callback_data="admin_health")],
            [InlineKeyboardButton(text="🔴 Live Management", callback_data="live_management"),
             InlineKeyboardButton(text="📊 System Logs", callback_data="admin_logs")],
            [InlineKeyboardButton(text="🗳️ Poll Manager", callback_data="poll_manager"),
             InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def account_management() -> InlineKeyboardMarkup:
        """Account management keyboard"""
        buttons = [
            [InlineKeyboardButton(text="➕ Add Account", callback_data="add_account"),
             InlineKeyboardButton(text="📋 List Accounts", callback_data="list_accounts")],
            [InlineKeyboardButton(text="🗑️ Remove Account", callback_data="remove_account"),
             InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_accounts")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def channel_control() -> InlineKeyboardMarkup:
        """Channel control keyboard"""
        buttons = [
            [InlineKeyboardButton(text="✅ Whitelist Channel", callback_data="channel_whitelist"),
             InlineKeyboardButton(text="❌ Blacklist Channel", callback_data="channel_blacklist")],
            [InlineKeyboardButton(text="📋 View Lists", callback_data="channel_lists"),
             InlineKeyboardButton(text="🗑️ Remove Entry", callback_data="channel_remove")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
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
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def boost_options(channel_id: int) -> InlineKeyboardMarkup:
        """Boost options for a specific channel"""
        buttons = [
            [InlineKeyboardButton(text="⚡ Instant Boost", callback_data=f"instant_boost:{channel_id}")],
            [InlineKeyboardButton(text="🎭 Emoji Reactions", callback_data=f"add_reactions:{channel_id}")],
            [InlineKeyboardButton(text="📊 Boost Stats", callback_data=f"boost_stats:{channel_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="boost_views")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Settings configuration menu"""
        buttons = [
            [InlineKeyboardButton(text="⚡ Performance Settings", callback_data="setting_delay")],
            [InlineKeyboardButton(text="📊 Auto Message Count", callback_data="setting_auto_count")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def delay_settings() -> InlineKeyboardMarkup:
        """Delay configuration options"""
        buttons = [
            [InlineKeyboardButton(text="🚀 Fast Mode", callback_data="delay_low"),
             InlineKeyboardButton(text="⚡ Balanced", callback_data="delay_medium")],
            [InlineKeyboardButton(text="🛡️ Safe Mode", callback_data="delay_high")],
            [InlineKeyboardButton(text="🔙 Settings", callback_data="settings")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def auto_count_settings() -> InlineKeyboardMarkup:
        """Auto message count configuration options"""
        buttons = [
            [InlineKeyboardButton(text="1 Message", callback_data="auto_count_1"),
             InlineKeyboardButton(text="2 Messages", callback_data="auto_count_2")],
            [InlineKeyboardButton(text="5 Messages", callback_data="auto_count_5"),
             InlineKeyboardButton(text="10 Messages", callback_data="auto_count_10")],
            [InlineKeyboardButton(text="20 Messages", callback_data="auto_count_20")],
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
            
            username = account.get("username")
            if username:
                display_name = f"@{username}" if not username.startswith('@') else username
            else:
                display_name = account.get("phone", "Unknown")
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{emoji} {display_name}",
                    callback_data=f"account_details:{account['id']}"
                )
            ])
        
        if not accounts:
            buttons.append([
                InlineKeyboardButton(text="➕ Add First Account", callback_data="add_account")
            ])
        
        buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="refresh_accounts"),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
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
            [InlineKeyboardButton(text="📊 All Logs", callback_data="logs_all"),
             InlineKeyboardButton(text="⚡ Boosts", callback_data="logs_boost")],
            [InlineKeyboardButton(text="🔗 Joins", callback_data="logs_join"),
             InlineKeyboardButton(text="⚠️ Errors", callback_data="logs_error")],
            [InlineKeyboardButton(text="🚫 Bans", callback_data="logs_ban"),
             InlineKeyboardButton(text="⏳ Flood Waits", callback_data="logs_flood_wait")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def live_management() -> InlineKeyboardMarkup:
        """Live Management keyboard"""
        buttons = [
            [InlineKeyboardButton(text="➕ Add Monitor Channel", callback_data="add_live_channel"),
             InlineKeyboardButton(text="📋 View Monitored", callback_data="view_live_channels")],
            [InlineKeyboardButton(text="🤖 Account Count", callback_data="configure_live_accounts"),
             InlineKeyboardButton(text="⚡ Monitor Status", callback_data="live_monitor_status")],
            [InlineKeyboardButton(text="🔴 Start Monitoring", callback_data="start_live_monitor"),
             InlineKeyboardButton(text="⏹️ Stop Monitoring", callback_data="stop_live_monitor")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def live_channel_list(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """Generate keyboard for monitored live channels list"""
        buttons = []
        
        for i, channel in enumerate(channels):
            channel_name = channel.get("title") or channel["channel_link"]
            if len(channel_name) > 25:
                channel_name = channel_name[:22] + "..."
            
            status_emoji = "🔴" if channel.get("active", False) else "⚫"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {channel_name}",
                    callback_data=f"live_channel_info:{channel['id']}"
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=f"remove_live_channel:{channel['id']}"
                )
            ])
        
        if not channels:
            buttons.append([
                InlineKeyboardButton(text="➕ Add Your First Monitor Channel", callback_data="add_live_channel")
            ])
        
        buttons.append([
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
        ])
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def live_account_selection(available_accounts: int) -> InlineKeyboardMarkup:
        """Generate keyboard for selecting number of accounts for live management"""
        buttons = []
        
        # Provide options based on available accounts
        if available_accounts >= 1:
            buttons.append([
                InlineKeyboardButton(text="1️⃣ 1 Account", callback_data="live_account_count:1")
            ])
        
        if available_accounts >= 2:
            buttons.append([
                InlineKeyboardButton(text="2️⃣ 2 Accounts", callback_data="live_account_count:2"),
                InlineKeyboardButton(text="3️⃣ 3 Accounts", callback_data="live_account_count:3") if available_accounts >= 3 else None
            ])
            # Remove None values
            buttons[-1] = [btn for btn in buttons[-1] if btn is not None]
        
        if available_accounts >= 5:
            buttons.append([
                InlineKeyboardButton(text="5️⃣ 5 Accounts", callback_data="live_account_count:5"),
                InlineKeyboardButton(text="🔟 10 Accounts", callback_data="live_account_count:10") if available_accounts >= 10 else None
            ])
            # Remove None values
            buttons[-1] = [btn for btn in buttons[-1] if btn is not None]
        
        if available_accounts >= 20:
            buttons.append([
                InlineKeyboardButton(text="2️⃣0️⃣ 20 Accounts", callback_data="live_account_count:20"),
                InlineKeyboardButton(text="5️⃣0️⃣ 50 Accounts", callback_data="live_account_count:50") if available_accounts >= 50 else None
            ])
            # Remove None values
            buttons[-1] = [btn for btn in buttons[-1] if btn is not None]
        
        if available_accounts >= 100:
            buttons.append([
                InlineKeyboardButton(text="💯 All Accounts", callback_data=f"live_account_count:{available_accounts}")
            ])
        elif available_accounts > 50:
            buttons.append([
                InlineKeyboardButton(text="💎 All Accounts", callback_data=f"live_account_count:{available_accounts}")
            ])
        
        # Add custom option
        buttons.append([
            InlineKeyboardButton(text="✏️ Custom Amount", callback_data="live_account_count:custom")
        ])
        
        buttons.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="live_management")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def poll_management() -> InlineKeyboardMarkup:
        """Poll Management keyboard"""
        buttons = [
            [InlineKeyboardButton(text="🗳️ Start Poll Voting", callback_data="start_poll_voting")],
            [InlineKeyboardButton(text="📋 Poll History", callback_data="poll_history")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def poll_options(poll_data: dict) -> InlineKeyboardMarkup:
        """Generate keyboard for poll options"""
        buttons = []
        
        if 'options' in poll_data:
            for i, option in enumerate(poll_data['options']):
                option_text = option.get('text', f'Option {i+1}')
                if len(option_text) > 30:
                    option_text = option_text[:27] + "..."
                
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗳️ {option_text}",
                        callback_data=f"vote_option:{i}"
                    )
                ])
        
        buttons.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="poll_manager"),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def view_count_selection(available_accounts: int, feature_type: str = "boost") -> InlineKeyboardMarkup:
        """Generate keyboard for selecting number of views based on available accounts"""
        buttons = []
        
        # Provide options based on available accounts
        if available_accounts >= 100:
            buttons.append([
                InlineKeyboardButton(text="💯 100 Views", callback_data=f"view_count:{feature_type}:100"),
                InlineKeyboardButton(text="🔥 250 Views", callback_data=f"view_count:{feature_type}:250")
            ])
        
        if available_accounts >= 500:
            buttons.append([
                InlineKeyboardButton(text="⚡ 500 Views", callback_data=f"view_count:{feature_type}:500"),
                InlineKeyboardButton(text="🚀 1000 Views", callback_data=f"view_count:{feature_type}:1000")
            ])
        
        if available_accounts >= 1000:
            buttons.append([
                InlineKeyboardButton(text="💎 All Accounts", callback_data=f"view_count:{feature_type}:{available_accounts}")
            ])
        
        # Always offer smaller options
        small_options = []
        if available_accounts >= 10:
            small_options.append(InlineKeyboardButton(text="🔟 10 Views", callback_data=f"view_count:{feature_type}:10"))
        if available_accounts >= 25:
            small_options.append(InlineKeyboardButton(text="2️⃣5️⃣ 25 Views", callback_data=f"view_count:{feature_type}:25"))
        if available_accounts >= 50:
            small_options.append(InlineKeyboardButton(text="5️⃣0️⃣ 50 Views", callback_data=f"view_count:{feature_type}:50"))
        
        if small_options:
            # Split into rows of 2
            for i in range(0, len(small_options), 2):
                row = small_options[i:i+2]
                buttons.append(row)
        
        buttons.append([
            InlineKeyboardButton(text="✏️ Custom Amount", callback_data=f"view_count:{feature_type}:custom")
        ])
        buttons.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"view_count_back:{feature_type}")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def time_selection(feature_type: str, view_count: int) -> InlineKeyboardMarkup:
        """Generate keyboard for selecting time intervals"""
        buttons = [
            [
                InlineKeyboardButton(text="⚡ 1 Min", callback_data=f"time_select:{feature_type}:{view_count}:1"),
                InlineKeyboardButton(text="🚀 5 Min", callback_data=f"time_select:{feature_type}:{view_count}:5")
            ],
            [
                InlineKeyboardButton(text="⏰ 10 Min", callback_data=f"time_select:{feature_type}:{view_count}:10"),
                InlineKeyboardButton(text="🕑 30 Min", callback_data=f"time_select:{feature_type}:{view_count}:30")
            ],
            [
                InlineKeyboardButton(text="🕐 1 Hour", callback_data=f"time_select:{feature_type}:{view_count}:60"),
                InlineKeyboardButton(text="🕕 2 Hours", callback_data=f"time_select:{feature_type}:{view_count}:120")
            ],
            [
                InlineKeyboardButton(text="🔄 Instant", callback_data=f"time_select:{feature_type}:{view_count}:0")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data=f"view_count_back:{feature_type}")
            ]
        ]
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def auto_options_selection(feature_type: str, view_count: int, time_minutes: int) -> InlineKeyboardMarkup:
        """Generate keyboard for auto/manual options selection"""
        buttons = [
            [
                InlineKeyboardButton(text="🤖 Auto Mode", callback_data=f"auto_option:{feature_type}:{view_count}:{time_minutes}:auto")
            ],
            [
                InlineKeyboardButton(text="✋ Manual Mode", callback_data=f"auto_option:{feature_type}:{view_count}:{time_minutes}:manual")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data=f"time_select_back:{feature_type}:{view_count}")
            ]
        ]
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    @staticmethod
    def account_count_display(available_accounts: int, feature_type: str = "boost") -> InlineKeyboardMarkup:
        """Display available accounts with continue button"""
        buttons = [
            [
                InlineKeyboardButton(text="▶️ Continue", callback_data=f"account_count_continue:{feature_type}")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="boost_views" if feature_type == "boost" else "emoji_reactions")
            ]
        ]
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
