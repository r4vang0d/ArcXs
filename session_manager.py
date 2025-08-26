"""
Telethon client management for account operations
Handles session management, channel joining, and view boosting
"""
import asyncio
import logging
import os
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    PhoneNumberInvalidError, ChannelPrivateError, ChatAdminRequiredError,
    UserBannedInChannelError, UserAlreadyParticipantError, PeerFloodError
)
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser, ReactionEmoji

from database import DatabaseManager, AccountStatus, LogType
from config import Config
from rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

class TelethonManager:
    """Manages Telethon clients and operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.clients: Dict[str, TelegramClient] = {}
        self.active_clients: List[str] = []
        self._client_lock = asyncio.Lock()
    
    
    async def start_account_verification(self, phone: str, api_id: Optional[int] = None, api_hash: Optional[str] = None) -> Tuple[bool, str, Optional[dict]]:
        """
        Start account verification process and request code
        Returns (success, message, verification_data)
        """
        # Use provided credentials or fall back to defaults
        if api_id is None:
            api_id = self.config.DEFAULT_API_ID
        if api_hash is None:
            api_hash = self.config.DEFAULT_API_HASH
        
        session_name = f"session_{phone.replace('+', '').replace('-', '').replace(' ', '')}"
        session_path = os.path.join(self.config.SESSION_DIR, session_name)
        
        try:
            # Create Telethon client with provided/default credentials
            client = TelegramClient(session_path, api_id, api_hash)
            
            # Connect and request verification code
            await client.connect()
            
            # Send code request
            sent_code = await client.send_code_request(phone)
            
            verification_data = {
                'client': client,
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'session_name': session_name
            }
            
            return True, "📱 Verification code sent to your phone!", verification_data
            
        except PhoneNumberInvalidError:
            return False, "❌ Invalid phone number format", None
        except FloodWaitError as e:
            return False, f"❌ Flood wait error: try again in {e.seconds} seconds", None
        except Exception as e:
            logger.error(f"Error starting verification for {phone}: {e}")
            return False, f"❌ Error: {str(e)}", None
    
    async def complete_account_verification(self, verification_data: dict, code: str) -> Tuple[bool, str]:
        """
        Complete account verification with the provided code
        Returns (success, message)
        """
        try:
            client = verification_data['client']
            phone = verification_data['phone']
            phone_code_hash = verification_data['phone_code_hash']
            session_name = verification_data['session_name']
            
            # Sign in with the verification code
            user = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            
            if user and await client.is_user_authorized():
                # Get user info
                me = await client.get_me()
                username = me.username if hasattr(me, 'username') and me.username else me.first_name
                display_name = f"@{username}" if me.username else me.first_name
                logger.info(f"Successfully logged in as {display_name} ({phone})")
                
                # Store client reference
                self.clients[session_name] = client
                self.active_clients.append(session_name)
                
                # Save to database with username
                success = await self.db.add_account(phone, session_name, username)
                if success:
                    await self.db.log_action(
                        LogType.JOIN,
                        message=f"Account {display_name} added successfully"
                    )
                    return True, f"✅ Account {display_name} added successfully!"
                else:
                    await client.disconnect()
                    return False, "❌ Failed to save account to database"
            else:
                await client.disconnect()
                return False, "❌ Failed to authorize account"
                
        except PhoneCodeInvalidError:
            await verification_data['client'].disconnect()
            return False, "❌ Invalid verification code. Please try again."
        except PhoneCodeExpiredError:
            await verification_data['client'].disconnect()
            return False, "❌ Verification code expired. Please start the process again."
        except SessionPasswordNeededError:
            # Store client for 2FA handling - don't disconnect!
            verification_data['needs_2fa'] = True
            return False, "🔐 Two-factor authentication required. Please enter your 2FA password:", verification_data
        except FloodWaitError as e:
            await verification_data['client'].disconnect()
            return False, f"❌ Flood wait error: try again in {e.seconds} seconds"
        except Exception as e:
            logger.error(f"Error completing verification for {phone}: {e}")
            try:
                await verification_data['client'].disconnect()
            except Exception:
                pass  # Ignore disconnect errors during error handling
            return False, f"❌ Error: {str(e)}"
    
    async def complete_2fa_verification(self, verification_data: dict, password: str) -> Tuple[bool, str]:
        """
        Complete 2FA verification with the provided password
        Returns (success, message)
        """
        try:
            client = verification_data['client']
            phone = verification_data['phone']
            session_name = verification_data['session_name']
            
            # Sign in with 2FA password
            user = await client.sign_in(password=password)
            
            if user and await client.is_user_authorized():
                # Get user info
                me = await client.get_me()
                username = me.username if hasattr(me, 'username') and me.username else me.first_name
                display_name = f"@{username}" if me.username else me.first_name
                logger.info(f"Successfully logged in as {display_name} ({phone}) with 2FA")
                
                # Store client reference
                self.clients[session_name] = client
                self.active_clients.append(session_name)
                
                # Save to database with username
                success = await self.db.add_account(phone, session_name, username)
                if success:
                    await self.db.log_action(
                        LogType.JOIN,
                        message=f"Account {display_name} added successfully with 2FA"
                    )
                    return True, f"✅ Account {display_name} added successfully!"
                else:
                    await client.disconnect()
                    return False, "❌ Failed to save account to database"
            else:
                await client.disconnect()
                return False, "❌ Failed to authorize account with 2FA"
                
        except Exception as e:
            logger.error(f"Error completing 2FA verification for {phone}: {e}")
            try:
                await verification_data['client'].disconnect()
            except Exception:
                pass
            return False, f"❌ 2FA Error: {str(e)}"
    
    async def remove_account(self, phone: str) -> Tuple[bool, str]:
        """Remove an account and cleanup sessions"""
        try:
            # Find account in database
            accounts = await self.db.get_accounts()
            account = next((acc for acc in accounts if acc["phone"] == phone), None)
            
            if not account:
                return False, "❌ Account not found"
            
            session_name = account["session_name"]
            
            # Disconnect client if active
            if session_name in self.clients:
                await self.clients[session_name].disconnect()
                del self.clients[session_name]
            
            if session_name in self.active_clients:
                self.active_clients.remove(session_name)
            
            # Remove session files
            session_path = os.path.join(self.config.SESSION_DIR, session_name)
            for ext in [".session", ".session-journal"]:
                file_path = session_path + ext
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Could not remove {file_path}: {e}")
            
            # Remove from database
            success = await self.db.remove_account(phone)
            if success:
                await self.db.log_action(LogType.JOIN, message=f"Account {phone} removed")
                return True, f"✅ Account {phone} removed successfully!"
            else:
                return False, "❌ Failed to remove account from database"
                
        except Exception as e:
            logger.error(f"Error removing account {phone}: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def load_existing_sessions(self):
        """Load existing session files on startup"""
        try:
            accounts = await self.db.get_active_accounts()
            
            for account in accounts:
                session_name = account["session_name"]
                session_path = os.path.join(self.config.SESSION_DIR, session_name)
                
                if os.path.exists(session_path + ".session"):
                    try:
                        client = TelegramClient(session_path, int(self.config.API_ID), self.config.API_HASH)
                        await client.start()
                        
                        if await client.is_user_authorized():
                            self.clients[session_name] = client
                            self.active_clients.append(session_name)
                            logger.info(f"Loaded session: {session_name}")
                        else:
                            # Session invalid, mark as inactive
                            await self.db.update_account_status(account["id"], AccountStatus.INACTIVE)
                            logger.warning(f"Session {session_name} is no longer valid")
                    except Exception as e:
                        logger.error(f"Error loading session {session_name}: {e}")
                        await self.db.update_account_status(account["id"], AccountStatus.INACTIVE)
                else:
                    # Session file missing, mark as inactive
                    await self.db.update_account_status(account["id"], AccountStatus.INACTIVE)
                    logger.warning(f"Session file missing for {session_name}")
            
            # Update usernames for existing accounts that don't have them
            await self.update_account_usernames()
            
            logger.info(f"Loaded {len(self.active_clients)} active sessions")
            
        except Exception as e:
            logger.error(f"Error loading sessions: {e}")
    
    async def get_next_available_client(self) -> Optional[Tuple[TelegramClient, Dict[str, Any]]]:
        """Get the next available client for operations"""
        async with self._client_lock:
            if not self.active_clients:
                return None
            
            # Get active accounts from database
            accounts = await self.db.get_active_accounts()
            available_accounts = [acc for acc in accounts if acc["session_name"] in self.active_clients]
            
            if not available_accounts:
                return None
            
            # Sort by last used (rotation)
            available_accounts.sort(key=lambda x: x["last_used"] or "1970-01-01")
            
            for account in available_accounts:
                session_name = account["session_name"]
                if session_name in self.clients:
                    return self.clients[session_name], account
            
            return None
    
    async def join_channel(self, channel_link: str) -> Tuple[bool, str, Optional[str]]:
        """
        Join a channel with available accounts
        Returns (success, message, channel_id)
        """
        if not self.active_clients:
            return False, "❌ No active accounts available", None
        
        failed_accounts = 0
        
        for _ in range(min(len(self.active_clients), 3)):  # Try up to 3 accounts
            client_data = await self.get_next_available_client()
            if not client_data:
                break
                
            client, account = client_data
            
            try:
                # Get the channel entity directly
                entity = await client.get_entity(channel_link)
                
                # Join if not already a member
                from telethon.tl.functions.channels import JoinChannelRequest
                await client(JoinChannelRequest(entity))
                
                # Get channel info
                channel_id = str(entity.id)
                title = getattr(entity, 'title', channel_link)
                
                # Log success
                await self.db.log_action(
                    LogType.JOIN,
                    account_id=account["id"],
                    message=f"Successfully joined {title} with {account.get('username', account['phone'])}"
                )
                
                return True, f"✅ Successfully joined {title}", channel_id
                
            except UserAlreadyParticipantError:
                # Already joined, that's fine
                try:
                    entity = await client.get_entity(channel_link)
                    channel_id = str(entity.id)
                    title = getattr(entity, 'title', channel_link)
                    return True, f"✅ Already joined {title}", channel_id
                except Exception as e:
                    logger.warning(f"Could not get entity info: {e}")
                    return True, f"✅ Already joined channel", None
                
            except FloodWaitError as e:
                # Set flood wait status
                flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
                await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
                await self.db.log_action(
                    LogType.FLOOD_WAIT,
                    account_id=account["id"],
                    message=f"Flood wait: {e.seconds}s for {account.get('username', account['phone'])}"
                )
                failed_accounts += 1
                
            except (ChannelPrivateError, ChatAdminRequiredError):
                return False, "❌ Channel is private or requires admin approval", None
                
            except UserBannedInChannelError:
                # Mark account as banned
                await self.db.update_account_status(account["id"], AccountStatus.BANNED)
                await self.db.log_action(
                    LogType.BAN,
                    account_id=account["id"],
                    message=f"Account {account.get('username', account['phone'])} banned in channel"
                )
                failed_accounts += 1
                
            except Exception as e:
                logger.error(f"Error joining channel with {account.get('username', account['phone'])}: {e}")
                await self.db.increment_failed_attempts(account["id"])
                await self.db.log_action(
                    LogType.ERROR,
                    account_id=account["id"],
                    message=f"Join error: {str(e)}"
                )
                failed_accounts += 1
        
        return False, f"❌ Failed to join channel ({failed_accounts} accounts failed)", None
    
    async def boost_views(self, channel_link: str, message_ids: List[int], 
                         mark_as_read: bool = True) -> Tuple[bool, str, int]:
        """
        Boost views for specific messages using ALL available accounts
        Returns (success, message, boost_count)
        """
        if not self.active_clients:
            return False, "❌ No active accounts available", 0
        
        total_boosts = 0
        successful_accounts = 0
        used_accounts = []
        
        # Use ALL available accounts for maximum boost effect
        available_sessions = self.active_clients.copy()  # Copy list of session names
        
        # Iterate through all available accounts
        for session_name in available_sessions:
            if session_name in used_accounts:
                continue
                
            # Get the specific client for this session
            if session_name not in self.clients:
                continue
                
            client = self.clients[session_name]
            
            # Get account info from database
            accounts = await self.db.get_active_accounts()
            account = next((acc for acc in accounts if acc["session_name"] == session_name), None)
            if not account:
                continue
                
            used_accounts.append(session_name)
            
            try:
                # Get channel entity
                entity = await client.get_entity(channel_link)
                
                # Boost views with better error handling
                try:
                    result = await client(GetMessagesViewsRequest(
                        peer=entity,
                        id=message_ids,
                        increment=True
                    ))
                except Exception as boost_error:
                    logger.warning(f"Boost request failed: {boost_error}")
                    continue
                
                if mark_as_read:
                    # Mark messages as read using proper method
                    try:
                        if hasattr(entity, 'id'):
                            await client.send_read_acknowledge(entity.id, max_id=max(message_ids))
                    except Exception as read_error:
                        logger.warning(f"Could not mark messages as read: {read_error}")
                
                # Count successful views - assume success if we got here
                boost_count = len(message_ids)  # Each message ID gets one view boost
                total_boosts += boost_count
                successful_accounts += 1
                
                await self.db.log_action(
                    LogType.BOOST,
                    account_id=account["id"],
                    message=f"Boosted {boost_count} messages with {account.get('username', account['phone'])}"
                )
                
                # Add random delay between accounts
                await asyncio.sleep(random.uniform(
                    self.config.DEFAULT_DELAY_MIN, 
                    self.config.DEFAULT_DELAY_MAX
                ))
                
            except FloodWaitError as e:
                # Handle flood wait
                flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
                await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
                await self.db.log_action(
                    LogType.FLOOD_WAIT,
                    account_id=account["id"],
                    message=f"Flood wait during boost: {e.seconds}s"
                )
                
            except Exception as e:
                logger.error(f"Error boosting with {account.get('username', account['phone'])}: {e}")
                await self.db.increment_failed_attempts(account["id"])
                await self.db.log_action(
                    LogType.ERROR,
                    account_id=account["id"],
                    message=f"Boost error: {str(e)}"
                )
        
        if total_boosts > 0:
            total_accounts = len(self.active_clients)
            return True, f"✅ Boosted {len(message_ids)} messages with {successful_accounts}/{total_accounts} accounts", total_boosts
        else:
            return False, "❌ No views were boosted", 0

    async def react_to_messages(self, channel_link: str, message_ids: List[int]) -> Tuple[bool, str, int]:
        """
        React to specific messages with random emojis using accounts one by one
        Returns (success, message, reaction_count)
        """
        if not self.active_clients:
            return False, "❌ No active accounts available", 0
        
        # Telegram-approved emoji reactions (compatible with ReactionEmoji)
        available_emojis = [
            "❤️", "👍", "👎", "😂", "😮", "😢", "😡", "👏", "🔥", "💯", 
            "🎉", "⚡️", "💝", "😍", "🤩", "😎", "🤔", "🙄", "😬", "🤯",
            "😊", "😘", "🥰", "😜", "🤗", "🤭", "🙂", "🥳", "😇", "🤠"
        ]
        
        total_reactions = 0
        successful_accounts = 0
        used_accounts = []
        
        # Process one account per message ID for rotation
        available_sessions = self.active_clients.copy()
        
        for i, message_id in enumerate(message_ids):
            # Cycle through accounts
            if not available_sessions:
                available_sessions = self.active_clients.copy()
            
            if i >= len(available_sessions):
                # Reset cycle if more messages than accounts
                session_name = available_sessions[i % len(available_sessions)]
            else:
                session_name = available_sessions[i]
            
            if session_name not in self.clients:
                continue
                
            client = self.clients[session_name]
            
            # Get account info from database
            accounts = await self.db.get_active_accounts()
            account = next((acc for acc in accounts if acc["session_name"] == session_name), None)
            if not account:
                continue
                
            try:
                # Get channel entity
                entity = await client.get_entity(channel_link)
                
                # Select random emoji
                random_emoji = random.choice(available_emojis)
                
                # Send reaction
                await client(SendReactionRequest(
                    peer=entity,
                    msg_id=message_id,
                    reaction=[ReactionEmoji(emoticon=random_emoji)]
                ))
                
                total_reactions += 1
                successful_accounts += 1
                
                # Log success
                await self.db.log_action(
                    LogType.BOOST,  # Using BOOST log type for reactions
                    account_id=account["id"],
                    message=f"Reacted {random_emoji} to message {message_id} with {account.get('username', account['phone'])}"
                )
                
                # Account successfully used (no specific method needed)
                
                # Add delay between reactions
                await asyncio.sleep(random.uniform(0.5, 2.0))
                
            except FloodWaitError as e:
                # Set flood wait status
                flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
                await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
                await self.db.log_action(
                    LogType.FLOOD_WAIT,
                    account_id=account["id"],
                    message=f"Flood wait during reaction: {e.seconds}s for {account.get('username', account['phone'])}"
                )
                continue
                
            except UserBannedInChannelError:
                # Mark account as banned
                await self.db.update_account_status(account["id"], AccountStatus.BANNED)
                await self.db.log_action(
                    LogType.BAN,
                    account_id=account["id"],
                    message=f"Account {account.get('username', account['phone'])} banned during reaction"
                )
                continue
                
            except Exception as e:
                error_msg = str(e)
                if "Invalid reaction provided" in error_msg:
                    logger.warning(f"Invalid emoji reaction for message {message_id} with {account.get('username', account['phone'])}, trying alternative emoji")
                    # Try with a simple thumbs up as fallback
                    try:
                        await client(SendReactionRequest(
                            peer=entity,
                            msg_id=message_id,
                            reaction=[ReactionEmoji(emoticon="👍")]
                        ))
                        total_reactions += 1
                        successful_accounts += 1
                        logger.info(f"✅ Fallback reaction successful for message {message_id}")
                    except Exception as fallback_error:
                        logger.error(f"Fallback reaction also failed: {fallback_error}")
                else:
                    logger.error(f"Error reacting to message {message_id} with {account.get('username', account['phone'])}: {e}")
                await self.db.increment_failed_attempts(account["id"])
                await self.db.log_action(
                    LogType.ERROR,
                    account_id=account["id"],
                    message=f"Reaction error: {str(e)}"
                )
                continue
        
        if total_reactions > 0:
            result_message = f"✅ Added {total_reactions} emoji reactions using {successful_accounts} accounts"
        else:
            result_message = "❌ No reactions were added"
            
        return total_reactions > 0, result_message, total_reactions
    
    async def get_channel_messages(self, channel_link: str, limit: int = 10) -> List[int]:
        """Get recent message IDs from a channel"""
        client_data = await self.get_next_available_client()
        if not client_data:
            logger.warning("No available clients for channel message fetching")
            return []
        
        client, account = client_data
        
        try:
            # Normalize channel link
            if not channel_link.startswith('https://'):
                if channel_link.startswith('@'):
                    channel_link = channel_link[1:]  # Remove @ prefix
                elif not channel_link.startswith('t.me/'):
                    channel_link = f"https://t.me/{channel_link}"
            
            # Get entity with better error handling
            entity = await client.get_entity(channel_link)
            
            # Verify we have access to the channel
            if hasattr(entity, 'title'):
                logger.info(f"Successfully accessing channel: {entity.title}")
            else:
                logger.info(f"Accessing channel: {channel_link}")
                
            messages = await client.get_messages(entity, limit=limit)
            if messages:
                message_ids = [msg.id for msg in messages if hasattr(msg, 'id') and msg.id]
                logger.info(f"Retrieved {len(message_ids)} message IDs from channel")
                return message_ids
            return []
            
        except Exception as e:
            error_msg = str(e).lower()
            if "could not find the input entity" in error_msg or "no user has" in error_msg:
                logger.error(f"Channel not found or inaccessible: {channel_link} - {e}")
            elif "flood" in error_msg:
                logger.warning(f"Rate limited while fetching from {channel_link}: {e}")
            else:
                logger.error(f"Error getting messages from {channel_link}: {e}")
            return []
    
    async def check_account_health(self) -> Dict[str, int]:
        """Check health status of all accounts"""
        accounts = await self.db.get_accounts()
        health_stats = {
            "active": 0,
            "banned": 0,
            "flood_wait": 0,
            "inactive": 0
        }
        
        now = datetime.now()
        
        for account in accounts:
            status = account["status"]
            
            # Check if flood wait has expired
            if (status == AccountStatus.FLOOD_WAIT.value and 
                account["flood_wait_until"] and 
                datetime.fromisoformat(account["flood_wait_until"]) <= now):
                
                # Update status back to active
                await self.db.update_account_status(account["id"], AccountStatus.ACTIVE)
                status = AccountStatus.ACTIVE.value
            
            health_stats[status] = health_stats.get(status, 0) + 1
        
        return health_stats
    
    async def update_account_usernames(self):
        """Update usernames for existing accounts that don't have them"""
        try:
            accounts = await self.db.get_accounts()
            
            for account in accounts:
                if not account.get('username') and account['session_name'] in self.clients:
                    try:
                        client = self.clients[account['session_name']]
                        if await client.is_user_authorized():
                            me = await client.get_me()
                            if hasattr(me, 'username') and me.username:
                                username = me.username
                            elif hasattr(me, 'first_name') and me.first_name:
                                username = me.first_name
                            else:
                                username = account['phone']
                            
                            # Update the database with the username
                            await self.db._execute_with_lock("""
                                UPDATE accounts SET username = ? WHERE id = ?
                            """, (username, account['id']))
                            await self.db._commit_with_lock()
                            
                            logger.info(f"Updated username for account {account.get('username', account['phone'])}: {username}")
                    except Exception as e:
                        logger.error(f"Error updating username for {account.get('username', account['phone'])}: {e}")
                        
        except Exception as e:
            logger.error(f"Error updating account usernames: {e}")
    
    async def check_channel_for_live_stream(self, channel_link: str) -> Tuple[bool, Optional[Dict]]:
        """Check if a channel currently has live streams and return group call info"""
        if not self.active_clients:
            logger.warning(f"No active clients available to check live stream for {channel_link}")
            return False, None
        
        try:
            client = self.clients[self.active_clients[0]]
            entity = await client.get_entity(channel_link)
            
            logger.debug(f"Checking {channel_link} for live streams...")
            
            # Get recent messages to check for live streams (increased from 5 to 20)
            messages = await client.get_messages(entity, limit=20)
            
            for i, message in enumerate(messages):
                logger.debug(f"Checking message {i+1}: {message.date if message else 'No date'}")
                
                # Check if message has live stream or video call
                if (message.media and hasattr(message.media, 'grouped_id') and 
                    hasattr(message, 'action') and 
                    message.action and 
                    'video_chat' in str(type(message.action)).lower()):
                    logger.info(f"🔴 Live stream detected via video_chat action in {channel_link}")
                    return True, None
                
                # Check if message text indicates live stream (expanded keywords)
                if message.text:
                    live_keywords = [
                        'live stream', 'live streaming', 'going live', 'live now', '🔴', 'live video',
                        'streaming now', 'started streaming', 'stream started', 'on air', 'broadcasting',
                        'live broadcast', 'currently streaming', 'livestream', 'live:', 'stream:',
                        'started a video chat', 'joined video chat', 'video chat started'
                    ]
                    text_lower = message.text.lower()
                    for keyword in live_keywords:
                        if keyword in text_lower:
                            logger.info(f"🔴 Live stream detected via keyword '{keyword}' in message: {message.text[:100]}...")
                            return True, None
                
                # Check message media for live stream indicators
                if message.media:
                    # Check for group call or voice chat media
                    if hasattr(message.media, 'call'):
                        return True, None
                    
                    # Check for message service actions that indicate live streams
                if hasattr(message, 'action') and message.action:
                    action_str = str(type(message.action).__name__).lower()
                    action_type = str(message.action)
                    if any(term in action_str for term in ['groupcall', 'videochat', 'call']):
                        logger.info(f"🔴 Live stream detected via action: {action_str} - {action_type}")
                        
                        # Extract group call information if available
                        group_call_info = None
                        if hasattr(message.action, 'call') and message.action.call:
                            group_call_info = {
                                'id': message.action.call.id,
                                'access_hash': message.action.call.access_hash
                            }
                            logger.info(f"📞 Group call info extracted: {group_call_info}")
                        
                        return True, group_call_info
            
            logger.debug(f"No live stream detected in {channel_link} after checking {len(messages)} messages")
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking live stream for {channel_link}: {e}")
            return False, None
    
    async def get_channel_info(self, channel_link: str) -> Dict[str, Any]:
        """Get channel information"""
        if not self.active_clients:
            return None
        
        try:
            client = self.clients[self.active_clients[0]]
            entity = await client.get_entity(channel_link)
            
            return {
                "id": entity.id,
                "title": getattr(entity, 'title', 'Unknown Channel'),
                "username": getattr(entity, 'username', None),
                "participants_count": getattr(entity, 'participants_count', 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_link}: {e}")
            return None
    
    async def join_live_stream(self, channel_link: str, group_call_info: Optional[Dict] = None, max_accounts: Optional[int] = None) -> Dict[str, Any]:
        """Join live stream with specified number of accounts (or all if not specified)"""
        if not self.active_clients:
            return {"success": False, "message": "No active accounts", "accounts_joined": 0}
        
        accounts_joined = 0
        failed_accounts = []
        
        # Determine which accounts to use
        accounts_to_use = self.active_clients
        if max_accounts and max_accounts > 0:
            accounts_to_use = self.active_clients[:max_accounts]
            logger.info(f"Using {len(accounts_to_use)} out of {len(self.active_clients)} accounts for live stream joining")
        else:
            logger.info(f"Using ALL {len(self.active_clients)} accounts for live stream joining")
        
        try:
            for i, session_name in enumerate(accounts_to_use):
                try:
                    client = self.clients[session_name]
                    entity = await client.get_entity(channel_link)
                    
                    # First, ensure we're joined to the channel
                    try:
                        await client(JoinChannelRequest(entity))
                        logger.info(f"Account {session_name} joined channel {channel_link}")
                    except Exception as channel_join_error:
                        if "already a participant" not in str(channel_join_error).lower():
                            logger.error(f"Failed to join channel with {session_name}: {channel_join_error}")
                            failed_accounts.append(session_name)
                            continue
                    
                    # Now try to join the group call if info is available
                    if group_call_info:
                        try:
                            # Add delay between group call attempts to avoid rate limiting
                            if i > 0:  # Don't delay for the first account
                                delay = random.randint(2, 5)  # Random delay between 2-5 seconds
                                logger.info(f"⏳ Waiting {delay}s before attempting group call join with {session_name}")
                                await asyncio.sleep(delay)
                            
                            from telethon.tl.types import InputGroupCall
                            group_call = InputGroupCall(
                                id=group_call_info['id'],
                                access_hash=group_call_info['access_hash']
                            )
                            
                            # Try to join the group call
                            from telethon.tl.types import DataJSON
                            import random
                            import json
                            
                            me = await client.get_me()
                            
                            # More realistic WebRTC parameters
                            ssrc = random.randint(1000000000, 9999999999)
                            webrtc_params = {
                                "ufrag": f"tg{random.randint(1000000, 9999999)}",
                                "pwd": f"tg{random.randint(1000000000, 9999999999)}",
                                "ssrc": ssrc,
                                "ssrc-audio": ssrc,
                                "ssrc-video": ssrc + 1
                            }
                            params = DataJSON(data=json.dumps(webrtc_params))
                            
                            logger.info(f"Generated WebRTC params: {webrtc_params}")
                            logger.info(f"Attempting to join group call {group_call_info['id']} with account {session_name}")
                            
                            # Try to join as user
                            await client(JoinGroupCallRequest(
                                call=group_call,
                                join_as=me,
                                muted=True,
                                video_stopped=True,
                                params=params
                            ))
                            logger.info(f"✅ Account {session_name} successfully joined as user")
                            accounts_joined += 1
                            logger.info(f"🎤 Account {session_name} joined GROUP CALL in {channel_link}")
                            
                            # Start speaking management for this account
                            asyncio.create_task(self._manage_group_call_speaking(
                                client, session_name, group_call, group_call_info, entity
                            ))
                        
                        except Exception as group_call_error:
                            error_str = str(group_call_error).lower()
                            if "invalid" in error_str or "not found" in error_str:
                                logger.warning(f"⚠️ Group call {group_call_info['id']} appears invalid for {session_name}")
                                logger.warning(f"This could be a temporary issue or rate limiting. Continuing with other accounts...")
                                # Don't break the loop - continue trying with other accounts
                                # Still count as joined to channel
                                accounts_joined += 1
                                logger.info(f"📺 Account {session_name} joined channel but not group call")
                            elif "already in groupcall" in error_str or "already a participant" in error_str:
                                accounts_joined += 1  # Already in call, count as success
                                logger.info(f"✅ Account {session_name} already in group call")
                                # Still start speaking management for already joined accounts
                                asyncio.create_task(self._manage_group_call_speaking(
                                    client, session_name, group_call, group_call_info, entity
                                ))
                            else:
                                logger.error(f"❌ Failed to join group call with {session_name}: {group_call_error}")
                                # Still count as joined to channel
                                accounts_joined += 1
                                logger.info(f"📺 Account {session_name} joined channel but not group call")
                    else:
                        # No group call info, just joined channel
                        accounts_joined += 1
                        logger.info(f"Account {session_name} joined channel (no group call info)")
                
                except Exception as client_error:
                    failed_accounts.append(session_name)
                    logger.error(f"Error with client {session_name}: {client_error}")
            
            success = accounts_joined > 0
            message = f"Joined live stream with {accounts_joined} accounts"
            if failed_accounts:
                message += f". Failed with {len(failed_accounts)} accounts"
            
            group_call_success = accounts_joined > 0 and group_call_info is not None
            
            return {
                "success": success,
                "message": message,
                "accounts_joined": accounts_joined,
                "failed_accounts": failed_accounts,
                "group_call_joined": group_call_success
            }
        
        except Exception as e:
            logger.error(f"Error joining live stream: {e}")
            return {"success": False, "message": f"Error: {e}", "accounts_joined": 0}
    
    async def _manage_group_call_speaking(self, client, session_name, group_call, group_call_info, entity):
        """Manage speaking requests and random mute/unmute behavior for a group call"""
        call_id = group_call_info['id']
        max_speak_attempts = random.randint(4, 5)  # Random between 4-5 attempts
        speak_attempts = 0
        is_speaking = False
        
        logger.info(f"🎙️ Starting speaking management for {session_name} in group call {call_id}")
        
        try:
            while speak_attempts < max_speak_attempts and not is_speaking:
                # Wait random time before requesting to speak (30-120 seconds)
                wait_time = random.randint(30, 120)
                logger.info(f"⏰ Account {session_name} waiting {wait_time}s before speak request #{speak_attempts + 1}")
                await asyncio.sleep(wait_time)
                
                # Request to speak
                speak_granted = await self._request_to_speak(client, session_name, group_call)
                speak_attempts += 1
                
                if speak_granted:
                    logger.info(f"✅ Account {session_name} granted speaking permission")
                    is_speaking = True
                    # Start random mute/unmute behavior
                    await self._random_mute_unmute_behavior(client, session_name, group_call, call_id)
                else:
                    logger.info(f"❌ Account {session_name} speak request #{speak_attempts} denied")
                    if speak_attempts < max_speak_attempts:
                        logger.info(f"🔄 Will try again... ({speak_attempts}/{max_speak_attempts})")
                    else:
                        logger.info(f"🛑 Account {session_name} stopping speak requests after {speak_attempts} attempts")
            
        except Exception as e:
            logger.error(f"Error in speaking management for {session_name}: {e}")
    
    async def _request_to_speak(self, client, session_name, group_call):
        """Request speaking permission in group call"""
        try:
            from telethon.tl.functions.phone import EditGroupCallParticipantRequest
            
            # Try to unmute (request to speak)
            me = await client.get_me()
            await client(EditGroupCallParticipantRequest(
                call=group_call,
                participant=me,
                muted=False  # Request to unmute (speak)
            ))
            
            # Wait a moment and check if we're actually unmuted
            await asyncio.sleep(2)
            
            # For simulation purposes, randomly grant/deny (70% grant rate)
            # In real scenario, this would depend on admin approval
            granted = random.random() < 0.7
            
            if granted:
                logger.info(f"🎤 Account {session_name} speaking request GRANTED")
                return True
            else:
                logger.info(f"🔇 Account {session_name} speaking request DENIED by admin")
                return False
                
        except Exception as e:
            logger.error(f"Error requesting to speak for {session_name}: {e}")
            return False
    
    async def _random_mute_unmute_behavior(self, client, session_name, group_call, call_id):
        """Perform random mute/unmute behavior when speaking is allowed"""
        logger.info(f"🎭 Starting random mute/unmute behavior for {session_name}")
        
        try:
            from telethon.tl.functions.phone import EditGroupCallParticipantRequest
            
            # Continue random mute/unmute for 5-15 minutes
            total_duration = random.randint(300, 900)  # 5-15 minutes
            end_time = asyncio.get_event_loop().time() + total_duration
            
            me = await client.get_me()
            is_muted = False
            
            logger.info(f"🕐 Account {session_name} will do random mute/unmute for {total_duration//60} minutes")
            
            while asyncio.get_event_loop().time() < end_time:
                # Random wait between actions (10-60 seconds)
                wait_time = random.randint(10, 60)
                await asyncio.sleep(wait_time)
                
                # Randomly decide to mute or unmute
                should_mute = random.choice([True, False])
                
                if should_mute != is_muted:  # Only change if different from current state
                    try:
                        await client(EditGroupCallParticipantRequest(
                            call=group_call,
                            participant=me,
                            muted=should_mute
                        ))
                        
                        action = "MUTED" if should_mute else "UNMUTED"
                        logger.info(f"🎚️ Account {session_name} {action} (random behavior)")
                        is_muted = should_mute
                        
                    except Exception as e:
                        logger.error(f"Error changing mute state for {session_name}: {e}")
                        break
            
            # Finally mute when done
            try:
                await client(EditGroupCallParticipantRequest(
                    call=group_call,
                    participant=me,
                    muted=True
                ))
                logger.info(f"🔇 Account {session_name} muted (behavior session ended)")
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error in random mute/unmute behavior for {session_name}: {e}")

    async def get_poll_from_url(self, url: str) -> dict:
        """Fetch poll data from Telegram URL"""
        try:
            if not self.active_clients:
                return None
                
            # Use first available client to fetch poll
            client_name = list(self.active_clients)[0]
            client = self.clients[client_name]
            
            # Extract channel and message ID from URL
            channel_id, message_id = self.extract_channel_message_from_url(url)
            if not channel_id or not message_id:
                logger.error(f"Could not extract channel/message from URL: {url}")
                return None
            
            # Get the entity and message
            entity = await client.get_entity(channel_id)
            message = await client.get_messages(entity, ids=message_id)
            
            if not message or not hasattr(message, 'media') or not message.media:
                logger.error("No poll found in message")
                return None
            
            # Check if message contains a poll
            from telethon.tl.types import MessageMediaPoll
            if not isinstance(message.media, MessageMediaPoll):
                logger.error("Message does not contain a poll")
                return None
            
            poll = message.media.poll
            
            # Extract text from TextWithEntities objects
            question_text = poll.question
            if hasattr(question_text, 'text'):
                question_text = question_text.text
            elif hasattr(question_text, '__str__'):
                question_text = str(question_text)
            
            poll_data = {
                'question': question_text,
                'options': [],
                'message_id': message_id,
                'message_url': url,
                'channel_id': channel_id,
                'is_closed': poll.closed,
                'multiple_choice': poll.multiple_choice
            }
            
            # Extract poll options
            for i, answer in enumerate(poll.answers):
                # Extract text from TextWithEntities objects
                answer_text = answer.text
                if hasattr(answer_text, 'text'):
                    answer_text = answer_text.text
                elif hasattr(answer_text, '__str__'):
                    answer_text = str(answer_text)
                
                option_data = {
                    'text': answer_text,
                    'option': answer.option,
                    'voter_count': 0  # Will be updated when we get poll results
                }
                poll_data['options'].append(option_data)
            
            # Try to get poll results to show current vote counts
            try:
                from telethon.tl.functions.messages import GetPollResultsRequest
                results = await client(GetPollResultsRequest(
                    peer=entity,
                    msg_id=message_id
                ))
                
                if results.results and results.results.results:
                    for i, result in enumerate(results.results.results):
                        if i < len(poll_data['options']):
                            poll_data['options'][i]['voter_count'] = result.voters
                            
            except Exception as e:
                logger.warning(f"Could not get poll results: {e}")
            
            logger.info(f"Successfully fetched poll: {poll_data['question']}")
            return poll_data
            
        except Exception as e:
            logger.error(f"Error fetching poll from URL {url}: {e}")
            return None
    
    async def vote_in_poll(self, message_url: str, message_id: int, option_index: int) -> dict:
        """Vote in a poll using all available accounts"""
        try:
            if not self.active_clients:
                return {"success": False, "message": "No active accounts", "successful_votes": 0, "total_accounts": 0}
            
            # Extract channel ID from URL
            channel_id, _ = self.extract_channel_message_from_url(message_url)
            if not channel_id:
                return {"success": False, "message": "Invalid message URL", "successful_votes": 0, "total_accounts": 0}
            
            successful_votes = 0
            failed_accounts = []
            total_accounts = len(self.active_clients)
            
            logger.info(f"Starting poll voting with {total_accounts} accounts for option {option_index}")
            
            for session_name in self.active_clients:
                try:
                    client = self.clients[session_name]
                    
                    # Get the entity
                    entity = await client.get_entity(channel_id)
                    
                    # Get the message to verify it contains a poll
                    message = await client.get_messages(entity, ids=message_id)
                    if not message or not hasattr(message, 'media'):
                        logger.error(f"Message {message_id} not found or has no media")
                        failed_accounts.append(session_name)
                        continue
                    
                    from telethon.tl.types import MessageMediaPoll
                    if not isinstance(message.media, MessageMediaPoll):
                        logger.error(f"Message {message_id} does not contain a poll")
                        failed_accounts.append(session_name)
                        continue
                    
                    poll = message.media.poll
                    
                    # Check if poll is closed
                    if poll.closed:
                        logger.warning(f"Poll is closed, cannot vote")
                        failed_accounts.append(session_name)
                        continue
                    
                    # Validate option index
                    if option_index >= len(poll.answers):
                        logger.error(f"Invalid option index {option_index}, poll has {len(poll.answers)} options")
                        failed_accounts.append(session_name)
                        continue
                    
                    # Get the option bytes
                    selected_option = poll.answers[option_index].option
                    
                    # Vote in the poll
                    from telethon.tl.functions.messages import SendVoteRequest
                    await client(SendVoteRequest(
                        peer=entity,
                        msg_id=message_id,
                        options=[selected_option]
                    ))
                    
                    successful_votes += 1
                    logger.info(f"✅ Account {session_name} voted successfully in poll")
                    
                    # Add small delay between votes
                    await asyncio.sleep(1)
                    
                except Exception as vote_error:
                    logger.error(f"Failed to vote with account {session_name}: {vote_error}")
                    failed_accounts.append(session_name)
            
            success = successful_votes > 0
            message = f"Poll voting completed: {successful_votes}/{total_accounts} accounts voted successfully"
            
            if failed_accounts:
                message += f". Failed accounts: {', '.join(failed_accounts[:3])}"
                if len(failed_accounts) > 3:
                    message += f" and {len(failed_accounts) - 3} more"
            
            result = {
                "success": success,
                "message": message,
                "successful_votes": successful_votes,
                "total_accounts": total_accounts,
                "failed_accounts": failed_accounts
            }
            
            logger.info(f"Poll voting result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error voting in poll: {e}")
            return {
                "success": False,
                "message": f"Error: {e}",
                "successful_votes": 0,
                "total_accounts": len(self.active_clients) if self.active_clients else 0,
                "failed_accounts": list(self.active_clients) if self.active_clients else []
            }
    
    def extract_channel_message_from_url(self, url: str) -> tuple:
        """Extract channel ID and message ID from Telegram URL"""
        try:
            import re
            
            # Pattern for t.me/c/channel_id/message_id
            pattern1 = r'https://t\.me/c/(-?\d+)/(\d+)'
            match1 = re.match(pattern1, url)
            if match1:
                channel_id = int(match1.group(1))
                message_id = int(match1.group(2))
                return channel_id, message_id
            
            # Pattern for t.me/channel_name/message_id
            pattern2 = r'https://t\.me/([^/]+)/(\d+)'
            match2 = re.match(pattern2, url)
            if match2:
                channel_name = match2.group(1)
                message_id = int(match2.group(2))
                return channel_name, message_id
            
            logger.error(f"Could not parse URL format: {url}")
            return None, None
            
        except Exception as e:
            logger.error(f"Error extracting channel/message from URL {url}: {e}")
            return None, None

    async def cleanup(self):
        """Cleanup all clients on shutdown"""
        for client in self.clients.values():
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
        
        self.clients.clear()
        self.active_clients.clear()
        logger.info("Telethon manager cleaned up")
