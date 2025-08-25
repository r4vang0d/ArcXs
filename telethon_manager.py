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
    FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneNumberInvalidError, ChannelPrivateError, ChatAdminRequiredError,
    UserBannedInChannelError, UserAlreadyParticipantError, PeerFloodError
)
from telethon.tl.functions.messages import GetMessagesViewsRequest
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

from database import DatabaseManager, AccountStatus, LogType
from config import Config

logger = logging.getLogger(__name__)

class TelethonManager:
    """Manages Telethon clients and operations"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.clients: Dict[str, TelegramClient] = {}
        self.active_clients: List[str] = []
        self._client_lock = asyncio.Lock()
    
    async def add_account_interactive(self, phone: str) -> Tuple[bool, str]:
        """
        Add a new account via interactive phone login
        Returns (success, message)
        """
        session_name = f"session_{phone.replace('+', '').replace('-', '').replace(' ', '')}"
        session_path = os.path.join(self.config.SESSION_DIR, session_name)
        
        try:
            # Create Telethon client
            client = TelegramClient(session_path, self.config.API_ID, self.config.API_HASH)
            
            # Start the client
            await client.start(phone=phone)
            
            if await client.is_user_authorized():
                # Get user info
                me = await client.get_me()
                logger.info(f"Successfully logged in as {me.first_name} ({phone})")
                
                # Store client reference
                self.clients[session_name] = client
                self.active_clients.append(session_name)
                
                # Save to database
                success = await self.db.add_account(phone, session_name)
                if success:
                    await self.db.log_action(
                        LogType.JOIN,
                        message=f"Account {phone} ({me.first_name}) added successfully"
                    )
                    return True, f"✅ Account {phone} added successfully!"
                else:
                    await client.disconnect()
                    return False, "❌ Failed to save account to database"
            else:
                await client.disconnect()
                return False, "❌ Failed to authorize account"
                
        except PhoneNumberInvalidError:
            return False, "❌ Invalid phone number format"
        except FloodWaitError as e:
            return False, f"❌ Flood wait error: try again in {e.seconds} seconds"
        except SessionPasswordNeededError:
            return False, "❌ Two-factor authentication detected. Please disable 2FA temporarily"
        except Exception as e:
            logger.error(f"Error adding account {phone}: {e}")
            return False, f"❌ Error: {str(e)}"
    
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
                        client = TelegramClient(session_path, self.config.API_ID, self.config.API_HASH)
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
                # Join the channel
                result = await client(events.common.resolve_peer(channel_link))
                entity = await client.get_entity(result)
                
                # Join if not already a member
                await client(events.common.JoinChannelRequest(entity))
                
                # Get channel info
                channel_id = str(entity.id)
                title = getattr(entity, 'title', channel_link)
                
                # Log success
                await self.db.log_action(
                    LogType.JOIN,
                    account_id=account["id"],
                    message=f"Successfully joined {title} with {account['phone']}"
                )
                
                return True, f"✅ Successfully joined {title}", channel_id
                
            except UserAlreadyParticipantError:
                # Already joined, that's fine
                try:
                    entity = await client.get_entity(channel_link)
                    channel_id = str(entity.id)
                    title = getattr(entity, 'title', channel_link)
                    return True, f"✅ Already joined {title}", channel_id
                except:
                    return True, f"✅ Already joined channel", None
                
            except FloodWaitError as e:
                # Set flood wait status
                flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
                await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
                await self.db.log_action(
                    LogType.FLOOD_WAIT,
                    account_id=account["id"],
                    message=f"Flood wait: {e.seconds}s for {account['phone']}"
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
                    message=f"Account {account['phone']} banned in channel"
                )
                failed_accounts += 1
                
            except Exception as e:
                logger.error(f"Error joining channel with {account['phone']}: {e}")
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
        Boost views for specific messages
        Returns (success, message, boost_count)
        """
        if not self.active_clients:
            return False, "❌ No active accounts available", 0
        
        total_boosts = 0
        successful_accounts = 0
        
        # Use all available accounts for boosting
        for session_name in self.active_clients[:]:  # Copy list to avoid modification issues
            client_data = await self.get_next_available_client()
            if not client_data:
                break
                
            client, account = client_data
            
            try:
                # Get channel entity
                entity = await client.get_entity(channel_link)
                
                # Boost views
                result = await client(GetMessagesViewsRequest(
                    peer=entity,
                    id=message_ids,
                    increment=True
                ))
                
                if mark_as_read:
                    # Mark messages as read
                    await client.send_read_acknowledge(entity, message_ids)
                
                # Count successful views
                if hasattr(result, 'views') and result.views:
                    boost_count = len([v for v in result.views if v and v > 0])
                    total_boosts += boost_count
                    successful_accounts += 1
                    
                    await self.db.log_action(
                        LogType.BOOST,
                        account_id=account["id"],
                        message=f"Boosted {boost_count} messages with {account['phone']}"
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
                logger.error(f"Error boosting with {account['phone']}: {e}")
                await self.db.increment_failed_attempts(account["id"])
                await self.db.log_action(
                    LogType.ERROR,
                    account_id=account["id"],
                    message=f"Boost error: {str(e)}"
                )
        
        if total_boosts > 0:
            return True, f"✅ Boosted views with {successful_accounts} accounts", total_boosts
        else:
            return False, "❌ No views were boosted", 0
    
    async def get_channel_messages(self, channel_link: str, limit: int = 10) -> List[int]:
        """Get recent message IDs from a channel"""
        client_data = await self.get_next_available_client()
        if not client_data:
            return []
        
        client, _ = client_data
        
        try:
            entity = await client.get_entity(channel_link)
            messages = await client.get_messages(entity, limit=limit)
            return [msg.id for msg in messages if msg.id]
        except Exception as e:
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
    
    async def cleanup(self):
        """Cleanup all clients on shutdown"""
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
        
        self.clients.clear()
        self.active_clients.clear()
        logger.info("Telethon manager cleaned up")
