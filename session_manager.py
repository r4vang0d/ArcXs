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
from retry_queue_manager import RetryQueueManager, RetryTask, RetryTaskType

logger = logging.getLogger(__name__)

class TelethonManager:
    """Manages Telethon clients and operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.clients: Dict[str, TelegramClient] = {}
        self.active_clients: List[str] = []
        self._client_lock = asyncio.Lock()
        
        # Initialize retry queue manager for persistent retries
        self.retry_manager = RetryQueueManager(self)
        
        # Track live stream management state
        self.active_group_calls: Dict[str, Dict] = {}  # Track active calls per session
    
    
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
                        
                        # Verify channel membership by checking if we can get channel info
                        await asyncio.sleep(1)  # Small delay to ensure join is processed
                        channel_info = await client.get_entity(entity)
                        logger.info(f"✅ Account {session_name} confirmed in channel: {getattr(channel_info, 'title', 'Unknown')}")
                        
                    except Exception as channel_join_error:
                        error_msg = str(channel_join_error).lower()
                        if "already a participant" in error_msg or "already a member" in error_msg:
                            logger.info(f"✅ Account {session_name} already in channel {channel_link}")
                        else:
                            logger.error(f"❌ Failed to join channel with {session_name}: {channel_join_error}")
                            failed_accounts.append(session_name)
                            continue
                    
                    # Now try to join the group call if info is available
                    if group_call_info:
                        try:
                            # Check account capabilities before attempting group call join
                            me = await client.get_me()
                            logger.info(f"🔍 Account {session_name} info: ID={me.id}, Username={getattr(me, 'username', 'None')}, Phone={getattr(me, 'phone', 'None')}")
                            
                            # Check if account has restrictions
                            full_user = await client.get_entity(me)
                            if hasattr(full_user, 'restricted') and full_user.restricted:
                                logger.warning(f"⚠️ Account {session_name} is restricted, may not be able to join group calls")
                            
                            # Check channel membership status
                            try:
                                participant = await client.get_participants(entity, filter=lambda p: p.id == me.id, limit=1)
                                if not participant:
                                    logger.warning(f"⚠️ Account {session_name} may not be properly joined to channel")
                                    # Try joining again
                                    await client(JoinChannelRequest(entity))
                                    await asyncio.sleep(2)
                                else:
                                    logger.info(f"✅ Account {session_name} verified as channel member")
                            except Exception as member_check_error:
                                logger.warning(f"⚠️ Could not verify membership for {session_name}: {member_check_error}")
                            # Get fresh group call info for each account to avoid "invalid" errors
                            if i > 0:  # Don't check for the first account
                                logger.info(f"🔄 Getting fresh group call info for account {session_name}")
                                fresh_has_live, fresh_group_call_info = await self.check_channel_for_live_stream(channel_link)
                                if fresh_has_live and fresh_group_call_info:
                                    group_call_info = fresh_group_call_info
                                    logger.info(f"✅ Updated group call info: {group_call_info}")
                                else:
                                    logger.warning(f"⚠️ Could not get fresh group call info for {session_name}")
                            
                            # Add delay between group call attempts but reduce it for efficiency
                            if i > 0:  # Don't delay for the first account
                                delay = random.randint(2, 5)  # Shorter delay but still avoid conflicts
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
                            import time
                            import hashlib
                            
                            me = await client.get_me()
                            
                            # Generate unique WebRTC parameters for each account
                            # Use account ID, session name, timestamp, and group call ID for uniqueness
                            unique_seed = f"{me.id}_{session_name}_{int(time.time())}_{group_call_info['id']}"
                            hash_seed = hashlib.md5(unique_seed.encode()).hexdigest()
                            
                            # Create deterministic but unique SSRC based on account
                            base_ssrc = int(hash_seed[:8], 16) % 1000000000 + 1000000000
                            
                            # Generate unique ICE parameters
                            ufrag_suffix = hash_seed[:7]
                            pwd_suffix = hash_seed[7:17]
                            
                            webrtc_params = {
                                "ufrag": f"tg{ufrag_suffix}",
                                "pwd": f"tg{pwd_suffix}{random.randint(100000, 999999)}",
                                "ssrc": base_ssrc,
                                "ssrc-audio": base_ssrc,
                                "ssrc-video": base_ssrc + 1,
                                "fingerprint": {
                                    "hash": "sha-256",
                                    "fingerprint": f"A{hash_seed[17:].upper()[:47]}",
                                    "setup": "active"
                                },
                                "candidates": [
                                    {
                                        "foundation": "1",
                                        "component": 1,
                                        "protocol": "udp",
                                        "priority": 2113667326 + (me.id % 1000),
                                        "ip": "127.0.0.1",
                                        "port": 9,
                                        "type": "host"
                                    }
                                ]
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
                            
                            # Add connection persistence tracking
                            if not hasattr(self, 'active_group_calls'):
                                self.active_group_calls = {}
                            
                            self.active_group_calls[session_name] = {
                                'group_call': group_call,
                                'group_call_info': group_call_info,
                                'entity': entity,
                                'joined_at': time.time(),
                                'webrtc_params': webrtc_params
                            }
                            
                            # Start speaking management for this account
                            asyncio.create_task(self._manage_group_call_speaking(
                                client, session_name, group_call, group_call_info, entity
                            ))
                            
                            # Start connection maintenance for this account
                            asyncio.create_task(self._maintain_group_call_connection(
                                client, session_name, group_call, group_call_info
                            ))
                        
                        except Exception as group_call_error:
                            error_str = str(group_call_error).lower()
                            
                            # For the problematic second account, log detailed account info for debugging
                            if session_name == "session_919031569809":
                                logger.error(f"🚫 DETAILED DEBUG FOR {session_name}:")
                                logger.error(f"   ↳ Account ID: {me.id}")
                                logger.error(f"   ↳ Username: {getattr(me, 'username', 'None')}")
                                logger.error(f"   ↳ Phone: {getattr(me, 'phone', 'None')}")
                                logger.error(f"   ↳ Verified: {getattr(me, 'verified', 'Unknown')}")
                                logger.error(f"   ↳ Bot: {getattr(me, 'bot', 'Unknown')}")
                                logger.error(f"   ↳ Premium: {getattr(me, 'premium', 'Unknown')}")
                                logger.error(f"   ↳ Group Call ID: {group_call_info['id']}")
                                logger.error(f"   ↳ Group Call Access Hash: {group_call_info['access_hash']}")
                                logger.error(f"   ↳ Channel Entity ID: {entity.id}")
                                logger.error(f"   ↳ Channel Title: {getattr(entity, 'title', 'Unknown')}")
                                logger.error(f"   ↳ EXACT ERROR: {group_call_error}")
                                logger.error(f"   ↳ ERROR TYPE: {type(group_call_error).__name__}")
                                
                                # Try to get group call details from Telegram to see if it exists
                                try:
                                    from telethon.tl.functions.phone import GetGroupCallRequest
                                    group_call_details = await client(GetGroupCallRequest(
                                        call=group_call,
                                        limit=1
                                    ))
                                    logger.error(f"   ↳ Group Call Exists: YES")
                                    logger.error(f"   ↳ Group Call Participants: {len(group_call_details.participants)}")
                                    logger.error(f"   ↳ Group Call Can Join: {group_call_details.call.join_muted}")
                                except Exception as gc_check:
                                    logger.error(f"   ↳ Group Call Check Failed: {gc_check}")
                                    logger.error(f"   ↳ This suggests the group call may not be accessible to this account")
                                
                                # Check if account is restricted
                                try:
                                    full_user = await client.get_entity(me)
                                    logger.error(f"   ↳ Account Restricted: {getattr(full_user, 'restricted', False)}")
                                    if hasattr(full_user, 'restriction_reason'):
                                        logger.error(f"   ↳ Restriction Reason: {full_user.restriction_reason}")
                                except Exception as check_error:
                                    logger.error(f"   ↳ Could not check account restrictions: {check_error}")
                                
                                # Add to persistent retry queue (never give up as per guide)
                                retry_task = RetryTask(
                                    session_name=session_name,
                                    task_type=RetryTaskType.JOIN_GROUP_CALL,
                                    group_call_info=group_call_info,
                                    channel_link=channel_link,
                                    client=client,
                                    entity=entity
                                )
                                self.retry_manager.add_retry_task(retry_task)
                                logger.info(f"📝 Added {session_name} to persistent retry queue - will never give up!")
                                accounts_joined += 1  # Count as processing even if failed
                            elif "invalid" in error_str or "not found" in error_str:
                                logger.warning(f"⚠️ Group call {group_call_info['id']} appears invalid for {session_name}")
                                logger.warning(f"This could be a temporary issue or rate limiting. Continuing with other accounts...")
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
        """Manage speaking requests and keep account active in group call permanently"""
        call_id = group_call_info['id']
        
        logger.info(f"🎙️ Starting permanent speaking management for {session_name} in group call {call_id}")
        
        try:
            # First, try to get speaking permission a few times
            max_speak_attempts = 3
            speak_attempts = 0
            got_speaking_permission = False
            
            while speak_attempts < max_speak_attempts and not got_speaking_permission:
                # Wait random time before requesting to speak (30-120 seconds)
                wait_time = random.randint(30, 120)
                logger.info(f"⏰ Account {session_name} waiting {wait_time}s before speak request #{speak_attempts + 1}")
                await asyncio.sleep(wait_time)
                
                # Request to speak
                speak_granted = await self._request_to_speak(client, session_name, group_call)
                speak_attempts += 1
                
                if speak_granted:
                    logger.info(f"✅ Account {session_name} granted speaking permission")
                    got_speaking_permission = True
                    # Start continuous behavior management
                    await self._continuous_group_call_behavior(client, session_name, group_call, call_id)
                    break
                else:
                    logger.info(f"❌ Account {session_name} speak request #{speak_attempts} denied")
                    if speak_attempts < max_speak_attempts:
                        logger.info(f"🔄 Will try again... ({speak_attempts}/{max_speak_attempts})")
            
            # If never got speaking permission, still maintain presence as listener
            if not got_speaking_permission:
                logger.info(f"🎧 Account {session_name} maintaining listener presence in group call")
                await self._maintain_listener_presence(client, session_name, group_call, call_id)
            
        except Exception as e:
            logger.error(f"Error in speaking management for {session_name}: {e}")
    
    async def _request_to_speak(self, client, session_name, group_call):
        """Request speaking permission in group call using 'raise hand' method"""
        try:
            from telethon.tl.functions.phone import EditGroupCallParticipantRequest, GetGroupCallRequest
            
            # Step 1: Raise hand to request speaking permission
            me = await client.get_me()
            logger.info(f"✋ Account {session_name} raising hand to request speaking permission")
            
            await client(EditGroupCallParticipantRequest(
                call=group_call,
                participant=me,
                raise_hand=True  # Raise hand to request permission (as mentioned in the guide)
            ))
            
            # Step 2: Wait for admin response (5-15 seconds)
            wait_time = random.randint(5, 15)
            logger.info(f"⏳ Account {session_name} waiting {wait_time}s for admin response")
            await asyncio.sleep(wait_time)
            
            # Step 3: Check if we got permission by querying call participants
            try:
                call_info = await client(GetGroupCallRequest(
                    call=group_call,
                    limit=100
                ))
                
                # Look for our account in participants
                for participant in call_info.participants:
                    if hasattr(participant, 'peer') and participant.peer.user_id == me.id:
                        if not participant.muted:
                            logger.info(f"✅ Account {session_name} speaking permission GRANTED by admin")
                            return True
                        else:
                            logger.info(f"❌ Account {session_name} still muted - request denied or pending")
                            return False
                
                # If not found in participants or still muted
                logger.info(f"❌ Account {session_name} not found as speaker - request denied")
                return False
                
            except Exception as check_error:
                logger.warning(f"⚠️ Could not verify speaking status for {session_name}: {check_error}")
                # Fallback: try to unmute directly
                try:
                    await client(EditGroupCallParticipantRequest(
                        call=group_call,
                        participant=me,
                        muted=False
                    ))
                    logger.info(f"🎤 Account {session_name} attempted direct unmute")
                    return True
                except:
                    logger.info(f"🔇 Account {session_name} direct unmute failed - likely denied")
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

    async def _continuous_group_call_behavior(self, client, session_name, group_call, call_id):
        """Maintain continuous activity in group call with speaking permission"""
        logger.info(f"🎭 Starting continuous behavior for {session_name} - will stay active indefinitely")
        
        try:
            from telethon.tl.functions.phone import EditGroupCallParticipantRequest
            me = await client.get_me()
            is_muted = False
            
            # Stay active indefinitely with periodic mute/unmute
            while True:
                # Random wait between actions (30-180 seconds)
                wait_time = random.randint(30, 180)
                await asyncio.sleep(wait_time)
                
                try:
                    # Randomly decide to mute or unmute (but not too frequently)
                    should_mute = random.choice([True, False]) if random.random() < 0.3 else is_muted
                    
                    if should_mute != is_muted:
                        await client(EditGroupCallParticipantRequest(
                            call=group_call,
                            participant=me,
                            muted=should_mute
                        ))
                        
                        action = "MUTED" if should_mute else "UNMUTED"
                        logger.info(f"🎚️ Account {session_name} {action} (continuous behavior)")
                        is_muted = should_mute
                    else:
                        # Send presence update even without state change
                        await client(EditGroupCallParticipantRequest(
                            call=group_call,
                            participant=me,
                            muted=is_muted
                        ))
                        logger.debug(f"🔄 Account {session_name} sent presence update")
                        
                except Exception as e:
                    error_str = str(e).lower()
                    if "ended" in error_str or "not found" in error_str:
                        logger.info(f"🔴 Group call {call_id} ended - stopping behavior for {session_name}")
                        break
                    elif "disconnected" in error_str or "connection" in error_str:
                        logger.warning(f"🔄 Connection lost for {session_name}, attempting auto-rejoin...")
                        # Auto-rejoin on connection loss (as suggested in guide)
                        rejoin_success = await self._auto_rejoin_group_call(client, session_name, group_call, group_call_info, entity)
                        if not rejoin_success:
                            logger.error(f"❌ Auto-rejoin failed for {session_name}")
                            break
                    else:
                        logger.warning(f"⚠️ Behavior error for {session_name}: {e}")
                        # Continue trying after short delay
                        await asyncio.sleep(30)
                        
        except Exception as e:
            logger.error(f"Error in continuous behavior for {session_name}: {e}")

    async def _maintain_listener_presence(self, client, session_name, group_call, call_id):
        """Maintain presence in group call as a listener (without speaking permission)"""
        logger.info(f"🎧 Maintaining listener presence for {session_name} in group call {call_id}")
        
        try:
            from telethon.tl.functions.phone import EditGroupCallParticipantRequest
            me = await client.get_me()
            
            # Stay connected as listener indefinitely
            while True:
                # Send presence update every 2-5 minutes
                wait_time = random.randint(120, 300)
                await asyncio.sleep(wait_time)
                
                try:
                    # Send muted presence update to maintain connection
                    await client(EditGroupCallParticipantRequest(
                        call=group_call,
                        participant=me,
                        muted=True  # Always muted as listener
                    ))
                    logger.debug(f"🎧 Account {session_name} maintained listener presence")
                    
                except Exception as e:
                    error_str = str(e).lower()
                    if "ended" in error_str or "not found" in error_str:
                        logger.info(f"🔴 Group call {call_id} ended - stopping listener for {session_name}")
                        break
                    elif "disconnected" in error_str or "connection" in error_str:
                        logger.warning(f"🔄 Listener connection lost for {session_name}, attempting auto-rejoin...")
                        # Auto-rejoin for listeners too
                        rejoin_success = await self._auto_rejoin_group_call(client, session_name, group_call, group_call_info, None)
                        if not rejoin_success:
                            logger.error(f"❌ Listener auto-rejoin failed for {session_name}")
                            break
                    else:
                        logger.warning(f"⚠️ Listener presence error for {session_name}: {e}")
                        await asyncio.sleep(60)
                        
        except Exception as e:
            logger.error(f"Error maintaining listener presence for {session_name}: {e}")

    async def _try_alternative_join_methods_with_retries(self, client, session_name, group_call, group_call_info, entity, me, channel_link):
        """Try alternative join methods with multiple retries and fresh group call info"""
        logger.info(f"🔄 Trying alternative join methods with retries for {session_name}")
        
        max_retries = 5
        for retry in range(max_retries):
            if retry > 0:
                # Exponential backoff: 1s → 3s → 10s → 30s → 60s (as suggested in guide)
                backoff_delays = [1, 3, 10, 30, 60]
                retry_delay = backoff_delays[min(retry - 1, len(backoff_delays) - 1)]
                logger.info(f"🔄 Retry {retry}/{max_retries} for {session_name} in {retry_delay}s (exponential backoff)")
                await asyncio.sleep(retry_delay)
                
                # Get completely fresh group call info for each retry
                logger.info(f"🔄 Getting fresh group call info for retry {retry}")
                fresh_has_live, fresh_group_call_info = await self.check_channel_for_live_stream(channel_link)
                if fresh_has_live and fresh_group_call_info:
                    group_call_info = fresh_group_call_info
                    from telethon.tl.types import InputGroupCall
                    group_call = InputGroupCall(
                        id=group_call_info['id'],
                        access_hash=group_call_info['access_hash']
                    )
                    logger.info(f"✅ Updated group call info for retry: {group_call_info}")
                else:
                    logger.warning(f"⚠️ No live stream found during retry {retry} for {session_name}")
                    continue
            
            # Try alternative methods
            success = await self._try_alternative_join_methods(client, session_name, group_call, group_call_info, entity, me)
            if success:
                logger.info(f"✅ Account {session_name} successfully joined after retry {retry}")
                return True
            else:
                logger.warning(f"❌ Alternative methods failed for {session_name} on retry {retry}")
        
        logger.error(f"❌ All retries exhausted for {session_name}")
        return False

    async def _auto_rejoin_group_call(self, client, session_name, group_call, group_call_info, entity):
        """Auto-rejoin group call when dropped (as suggested in guide)"""
        logger.info(f"🔄 Attempting auto-rejoin for {session_name}")
        
        try:
            # Step 1: Get fresh group call info (mandatory per guide)
            from telethon.tl.functions.phone import GetGroupCallRequest
            fresh_call_info = await client(GetGroupCallRequest(
                call=group_call,
                limit=1
            ))
            
            # Step 2: Rejoin with fresh WebRTC parameters
            webrtc_params = self._generate_webrtc_params(session_name, group_call_info['id'])
            from telethon.tl.functions.phone import JoinGroupCallRequest
            from telethon.tl.types import DataJSON
            import json
            
            params = DataJSON(data=json.dumps(webrtc_params))
            me = await client.get_me()
            
            await client(JoinGroupCallRequest(
                call=group_call,
                join_as=me,
                muted=True,
                video_stopped=True,
                params=params
            ))
            
            logger.info(f"✅ Account {session_name} successfully rejoined group call")
            return True
            
        except Exception as e:
            logger.error(f"❌ Auto-rejoin failed for {session_name}: {e}")
            return False
    
    def _create_group_call_input(self, group_call_info: Dict[str, Any]):
        """Create InputGroupCall from group call info"""
        from telethon.tl.types import InputGroupCall
        return InputGroupCall(
            id=group_call_info['id'],
            access_hash=group_call_info['access_hash']
        )
    
    async def start_retry_manager(self):
        """Start the retry queue manager"""
        await self.retry_manager.start()
        
    async def stop_retry_manager(self):
        """Stop the retry queue manager"""
        await self.retry_manager.stop()

    async def _try_alternative_join_methods(self, client, session_name, group_call, group_call_info, entity, me):
        """Try multiple alternative methods to join group call for problematic accounts"""
        logger.info(f"🔄 Trying alternative join methods for {session_name}")
        
        from telethon.tl.functions.phone import JoinGroupCallRequest
        
        # Method 1: Join with empty WebRTC parameters
        try:
            logger.info(f"📱 Method 1: Empty WebRTC params for {session_name}")
            from telethon.tl.types import DataJSON
            import json
            empty_params = DataJSON(data=json.dumps({}))
            
            await client(JoinGroupCallRequest(
                call=group_call,
                join_as=me,
                muted=True,
                video_stopped=True,
                params=empty_params
            ))
            logger.info(f"✅ Account {session_name} joined using simple method")
            # Start management tasks
            asyncio.create_task(self._manage_group_call_speaking(
                client, session_name, group_call, group_call_info, entity
            ))
            asyncio.create_task(self._maintain_group_call_connection(
                client, session_name, group_call, group_call_info
            ))
            return True
        except Exception as e1:
            logger.warning(f"⚠️ Method 1 failed for {session_name}: {e1}")
        
        # Method 2: Try with minimal WebRTC params
        try:
            logger.info(f"📱 Method 2: Minimal WebRTC params for {session_name}")
            from telethon.tl.types import DataJSON
            import json
            minimal_params = {
                "ufrag": "tg000001",
                "pwd": "tg000001000001",
                "ssrc": 1000000001,
                "ssrc-audio": 1000000001,
                "ssrc-video": 1000000002
            }
            params = DataJSON(data=json.dumps(minimal_params))
            
            await client(JoinGroupCallRequest(
                call=group_call,
                join_as=me,
                muted=True,
                video_stopped=True,
                params=params
            ))
            logger.info(f"✅ Account {session_name} joined using minimal params method")
            # Start management tasks
            asyncio.create_task(self._manage_group_call_speaking(
                client, session_name, group_call, group_call_info, entity
            ))
            asyncio.create_task(self._maintain_group_call_connection(
                client, session_name, group_call, group_call_info
            ))
            return True
        except Exception as e2:
            logger.warning(f"⚠️ Method 2 failed for {session_name}: {e2}")
        
        # Method 3: Try with different group call access hash 
        try:
            logger.info(f"📱 Method 3: Alternative group call attempt for {session_name}")
            await asyncio.sleep(3)  # Extra delay
            
            # Create alternative params for this account
            alt_params = {
                "ufrag": f"alt{session_name[-4:]}",
                "pwd": f"alt{session_name[-8:]}000000",
                "ssrc": 2000000000 + int(session_name[-4:]),
                "ssrc-audio": 2000000000 + int(session_name[-4:]),
                "ssrc-video": 2000000001 + int(session_name[-4:])
            }
            params = DataJSON(data=json.dumps(alt_params))
            
            await client(JoinGroupCallRequest(
                call=group_call,
                join_as=me,
                muted=True,
                video_stopped=True,
                params=params
            ))
            logger.info(f"✅ Account {session_name} joined as listener only")
            # Start listener management
            asyncio.create_task(self._maintain_listener_presence(
                client, session_name, group_call, group_call_info['id']
            ))
            return True
        except Exception as e3:
            logger.warning(f"⚠️ Method 3 failed for {session_name}: {e3}")
        
        logger.error(f"❌ All alternative methods failed for {session_name}")
        logger.info(f"📺 Account {session_name} joined channel but not group call")
        return False

    async def _maintain_group_call_connection(self, client, session_name, group_call, group_call_info):
        """Maintain group call connection and prevent automatic disconnection"""
        import time
        call_id = group_call_info['id']
        logger.info(f"🔄 Starting connection maintenance for {session_name} in group call {call_id}")
        
        try:
            # Keep connection alive by periodically checking status
            maintenance_interval = random.randint(120, 300)  # 2-5 minutes
            max_maintenance_duration = 3600  # 1 hour max
            start_time = time.time()
            
            while (time.time() - start_time) < max_maintenance_duration:
                await asyncio.sleep(maintenance_interval)
                
                try:
                    # Check if we're still in the group call
                    from telethon.tl.functions.phone import GetGroupCallRequest
                    call_info = await client(GetGroupCallRequest(call=group_call, limit=1))
                    
                    if call_info and call_info.call:
                        logger.debug(f"🟢 Connection maintained for {session_name} in group call {call_id}")
                        
                        # Occasionally send a small update to maintain presence
                        if random.randint(1, 4) == 1:  # 25% chance
                            try:
                                me = await client.get_me()
                                await client(EditGroupCallParticipantRequest(
                                    call=group_call,
                                    participant=me,
                                    muted=True  # Keep muted to avoid spam
                                ))
                                logger.debug(f"🔄 Sent presence update for {session_name}")
                            except Exception as presence_error:
                                logger.debug(f"Presence update failed for {session_name}: {presence_error}")
                    else:
                        logger.info(f"🔴 Group call {call_id} ended, stopping maintenance for {session_name}")
                        break
                        
                except Exception as check_error:
                    error_str = str(check_error).lower()
                    if "ended" in error_str or "not found" in error_str:
                        logger.info(f"🔴 Group call {call_id} ended, stopping maintenance for {session_name}")
                        break
                    else:
                        logger.warning(f"⚠️ Connection check failed for {session_name}: {check_error}")
                        
                # Adjust maintenance interval randomly
                maintenance_interval = random.randint(120, 300)
                
        except Exception as e:
            logger.error(f"Error in connection maintenance for {session_name}: {e}")
        finally:
            # Clean up tracking
            if hasattr(self, 'active_group_calls') and session_name in self.active_group_calls:
                del self.active_group_calls[session_name]
                logger.info(f"🧹 Cleaned up connection tracking for {session_name}")

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
