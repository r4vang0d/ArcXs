"""
High-Performance Telethon Manager for 2000+ Accounts
Features: Lazy Loading, Connection Pooling, Rate Limiting, Resource Management
"""
import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Set
from pathlib import Path
from collections import defaultdict, deque
import weakref

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    PhoneNumberInvalidError, ChannelPrivateError, ChatAdminRequiredError,
    UserBannedInChannelError, UserAlreadyParticipantError, PeerFloodError
)
from telethon.tl.functions.messages import GetMessagesViewsRequest
from telethon.tl.functions import channels
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

from database_pg import PostgreSQLManager, AccountStatus, LogType
from config import Config

logger = logging.getLogger(__name__)

class RateLimiter:
    """Advanced rate limiter for Telegram API calls"""
    
    def __init__(self, calls_per_minute: int = 30, calls_per_hour: int = 1000):
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour
        self.minute_calls = deque()
        self.hour_calls = deque()
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        async with self._lock:
            now = time.time()
            
            # Clean old calls
            while self.minute_calls and now - self.minute_calls[0] > 60:
                self.minute_calls.popleft()
            while self.hour_calls and now - self.hour_calls[0] > 3600:
                self.hour_calls.popleft()
            
            # Check limits and wait if needed
            if len(self.minute_calls) >= self.calls_per_minute:
                wait_time = 60 - (now - self.minute_calls[0])
                if wait_time > 0:
                    logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            
            if len(self.hour_calls) >= self.calls_per_hour:
                wait_time = 3600 - (now - self.hour_calls[0])
                if wait_time > 0:
                    logger.warning(f"Hour rate limit: waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            
            # Record this call
            self.minute_calls.append(now)
            self.hour_calls.append(now)

class ClientPool:
    """Manages a pool of Telethon clients with lazy loading"""
    
    def __init__(self, max_active_clients: int = 100, cleanup_interval: int = 300):
        self.max_active_clients = max_active_clients
        self.cleanup_interval = cleanup_interval
        self.active_clients: Dict[str, TelegramClient] = {}
        self.client_last_used: Dict[str, float] = {}
        self.client_locks: Dict[str, asyncio.Lock] = {}
        self._pool_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self.start_cleanup_task()
    
    def start_cleanup_task(self):
        """Start the cleanup task"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodically clean up unused clients"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_unused_clients()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
    
    async def get_client(self, session_name: str, api_id: int, api_hash: str, 
                        session_dir: str) -> Optional[TelegramClient]:
        """Get or create a client (lazy loading)"""
        async with self._pool_lock:
            # Update last used time
            self.client_last_used[session_name] = time.time()
            
            # Return existing client if available
            if session_name in self.active_clients:
                return self.active_clients[session_name]
            
            # Check if we need to cleanup before adding new client
            if len(self.active_clients) >= self.max_active_clients:
                await self._cleanup_least_used()
            
            # Create new client
            session_path = os.path.join(session_dir, session_name)
            client = TelegramClient(session_path, api_id, api_hash)
            
            try:
                await client.connect()
                if await client.is_user_authorized():
                    self.active_clients[session_name] = client
                    self.client_locks[session_name] = asyncio.Lock()
                    logger.debug(f"Loaded client: {session_name}")
                    return client
                else:
                    await client.disconnect()
                    return None
            except Exception as e:
                logger.error(f"Failed to load client {session_name}: {e}")
                await client.disconnect()
                return None
    
    async def _cleanup_least_used(self, count: int = 10):
        """Clean up least recently used clients"""
        if not self.active_clients:
            return
        
        # Sort by last used time
        sorted_clients = sorted(
            self.client_last_used.items(),
            key=lambda x: x[1]
        )
        
        to_remove = sorted_clients[:count]
        for session_name, _ in to_remove:
            await self._disconnect_client(session_name)
    
    async def cleanup_unused_clients(self, max_idle_time: int = 600):
        """Clean up clients that haven't been used recently"""
        current_time = time.time()
        to_remove = []
        
        for session_name, last_used in self.client_last_used.items():
            if current_time - last_used > max_idle_time:
                to_remove.append(session_name)
        
        for session_name in to_remove:
            await self._disconnect_client(session_name)
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} unused clients")
    
    async def _disconnect_client(self, session_name: str):
        """Safely disconnect and remove a client"""
        if session_name in self.active_clients:
            try:
                client = self.active_clients[session_name]
                await client.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting client {session_name}: {e}")
            finally:
                self.active_clients.pop(session_name, None)
                self.client_last_used.pop(session_name, None)
                self.client_locks.pop(session_name, None)
    
    async def get_client_lock(self, session_name: str) -> asyncio.Lock:
        """Get lock for a specific client"""
        if session_name not in self.client_locks:
            self.client_locks[session_name] = asyncio.Lock()
        return self.client_locks[session_name]
    
    async def close_all(self):
        """Close all active clients"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        for session_name in list(self.active_clients.keys()):
            await self._disconnect_client(session_name)
        
        logger.info("All clients disconnected")

class OptimizedTelethonManager:
    """High-performance Telethon manager for 2000+ accounts"""
    
    def __init__(self, config: Config, db_manager: PostgreSQLManager):
        self.config = config
        self.db = db_manager
        self.client_pool = ClientPool(max_active_clients=config.MAX_ACTIVE_CLIENTS)
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.global_rate_limiter = RateLimiter(calls_per_minute=150, calls_per_hour=5000)
        self._verification_data: Dict[str, Dict] = {}
        
        # Account rotation state
        self.account_rotation_index = 0
        self.failed_accounts: Set[str] = set()
        self.last_rotation_reset = time.time()
    
    async def get_rate_limiter(self, session_name: str) -> RateLimiter:
        """Get or create rate limiter for specific account"""
        if session_name not in self.rate_limiters:
            self.rate_limiters[session_name] = RateLimiter()
        return self.rate_limiters[session_name]
    
    async def start_account_verification(self, phone: str, api_id: Optional[int] = None, 
                                       api_hash: Optional[str] = None) -> Tuple[bool, str, Optional[dict]]:
        """Start account verification with rate limiting"""
        if api_id is None:
            api_id = self.config.DEFAULT_API_ID
        if api_hash is None:
            api_hash = self.config.DEFAULT_API_HASH
        
        session_name = f"session_{phone.replace('+', '').replace('-', '').replace(' ', '')}"
        
        # Rate limiting
        await self.global_rate_limiter.wait_if_needed()
        
        try:
            client = await self.client_pool.get_client(
                session_name, api_id, api_hash, self.config.SESSION_DIR
            )
            
            if client is None:
                session_path = os.path.join(self.config.SESSION_DIR, session_name)
                client = TelegramClient(session_path, api_id, api_hash)
                await client.connect()
            
            sent_code = await client.send_code_request(phone)
            
            verification_data = {
                'client': client,
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'session_name': session_name
            }
            
            self._verification_data[phone] = verification_data
            return True, "📱 Verification code sent to your phone!", verification_data
            
        except FloodWaitError as e:
            return False, f"❌ Flood wait: try again in {e.seconds} seconds", None
        except Exception as e:
            logger.error(f"Error starting verification for {phone}: {e}")
            return False, f"❌ Error: {str(e)}", None
    
    async def complete_account_verification(self, verification_data: dict, code: str) -> Tuple[bool, str]:
        """Complete account verification and add to database"""
        try:
            client = verification_data['client']
            phone = verification_data['phone']
            phone_code_hash = verification_data['phone_code_hash']
            session_name = verification_data['session_name']
            
            user = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            
            if user and await client.is_user_authorized():
                me = await client.get_me()
                username = me.username if hasattr(me, 'username') and me.username else me.first_name
                display_name = f"@{username}" if me.username else me.first_name
                
                # Add to database with priority
                priority = 1  # Default priority
                success = await self.db.add_account(phone, session_name, username, priority)
                
                if success:
                    logger.info(f"Successfully added account: {display_name} ({phone})")
                    # Don't keep client in pool immediately - will be loaded on demand
                    await client.disconnect()
                    
                    # Clean up verification data
                    self._verification_data.pop(phone, None)
                    
                    return True, f"✅ Account {display_name} added successfully!"
                else:
                    return False, "❌ Failed to save account to database"
            else:
                return False, "❌ Authentication failed"
                
        except PhoneCodeInvalidError:
            return False, "❌ Invalid verification code"
        except Exception as e:
            logger.error(f"Error completing verification: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def get_next_available_accounts(self, count: int = 10) -> List[Tuple[TelegramClient, Dict[str, Any]]]:
        """Get multiple available accounts with intelligent rotation"""
        accounts = await self.db.get_active_accounts(limit=count * 2, priority_order=True)
        
        if not accounts:
            return []
        
        # Reset rotation periodically
        if time.time() - self.last_rotation_reset > 3600:  # Reset every hour
            self.failed_accounts.clear()
            self.account_rotation_index = 0
            self.last_rotation_reset = time.time()
        
        available_pairs = []
        checked = 0
        
        # Try to get requested number of accounts
        while len(available_pairs) < count and checked < len(accounts):
            account = accounts[(self.account_rotation_index + checked) % len(accounts)]
            session_name = account["session_name"]
            
            # Skip recently failed accounts
            if session_name in self.failed_accounts:
                checked += 1
                continue
            
            try:
                client = await self.client_pool.get_client(
                    session_name, 
                    self.config.DEFAULT_API_ID,
                    self.config.DEFAULT_API_HASH,
                    self.config.SESSION_DIR
                )
                
                if client and await client.is_user_authorized():
                    available_pairs.append((client, account))
                else:
                    self.failed_accounts.add(session_name)
                    
            except Exception as e:
                logger.debug(f"Failed to load client {session_name}: {e}")
                self.failed_accounts.add(session_name)
            
            checked += 1
        
        # Update rotation index
        self.account_rotation_index = (self.account_rotation_index + checked) % len(accounts)
        
        return available_pairs
    
    async def join_channel(self, channel_link: str, max_accounts: int = 50) -> Tuple[bool, str, Optional[str]]:
        """Join channel with multiple accounts efficiently"""
        successful_accounts = 0
        failed_accounts = 0
        channel_id = None
        
        # Get accounts in batches to avoid loading too many at once
        batch_size = min(max_accounts, 20)
        accounts_processed = 0
        
        while accounts_processed < max_accounts and successful_accounts == 0:
            account_pairs = await self.get_next_available_accounts(batch_size)
            
            if not account_pairs:
                break
            
            for client, account in account_pairs:
                if accounts_processed >= max_accounts:
                    break
                
                session_name = account["session_name"]
                
                try:
                    # Rate limiting per account
                    rate_limiter = await self.get_rate_limiter(session_name)
                    await rate_limiter.wait_if_needed()
                    
                    # Global rate limiting
                    await self.global_rate_limiter.wait_if_needed()
                    
                    async with await self.client_pool.get_client_lock(session_name):
                        entity = await client.get_entity(channel_link)
                        
                        if not channel_id:
                            channel_id = str(entity.id) if hasattr(entity, 'id') else None
                        
                        # Try to join
                        await client(functions.channels.JoinChannelRequest(entity))
                        
                        successful_accounts += 1
                        
                        await self.db.log_action(
                            LogType.JOIN,
                            account_id=account["id"],
                            message=f"Joined channel with {account.get('username', account['phone'])}"
                        )
                        
                        # Add small delay between joins
                        await asyncio.sleep(random.uniform(1, 3))
                        
                except UserAlreadyParticipantError:
                    successful_accounts += 1  # Already joined counts as success
                    
                except FloodWaitError as e:
                    flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
                    await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
                    failed_accounts += 1
                    
                except (ChannelPrivateError, ChatAdminRequiredError):
                    return False, "❌ Channel is private or requires admin approval", None
                    
                except UserBannedInChannelError:
                    await self.db.update_account_status(account["id"], AccountStatus.BANNED)
                    failed_accounts += 1
                    
                except Exception as e:
                    logger.error(f"Error joining channel with {account.get('username', account['phone'])}: {e}")
                    failed_accounts += 1
                
                accounts_processed += 1
        
        if successful_accounts > 0:
            return True, f"✅ Joined channel with {successful_accounts} accounts", channel_id
        else:
            return False, f"❌ Failed to join channel ({failed_accounts} accounts failed)", None
    
    async def boost_views(self, channel_link: str, message_ids: List[int], 
                         mark_as_read: bool = True, max_accounts: int = 100) -> Tuple[bool, str, int]:
        """Boost views using multiple accounts with advanced optimization"""
        total_boosts = 0
        successful_accounts = 0
        failed_accounts = 0
        
        # Get accounts in batches
        batch_size = min(max_accounts, 50)
        accounts_processed = 0
        
        while accounts_processed < max_accounts:
            account_pairs = await self.get_next_available_accounts(batch_size)
            
            if not account_pairs:
                break
            
            # Process accounts in parallel batches
            tasks = []
            batch_accounts = account_pairs[:min(10, len(account_pairs))]  # Process 10 at a time
            
            for client, account in batch_accounts:
                task = self._boost_with_account(
                    client, account, channel_link, message_ids, mark_as_read
                )
                tasks.append(task)
            
            # Wait for batch completion
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failed_accounts += 1
                elif result:
                    successful_accounts += 1
                    total_boosts += len(message_ids)
                else:
                    failed_accounts += 1
            
            accounts_processed += len(batch_accounts)
            
            # Small delay between batches
            await asyncio.sleep(random.uniform(2, 5))
        
        if total_boosts > 0:
            return True, f"✅ Boosted {len(message_ids)} messages with {successful_accounts}/{accounts_processed} accounts", total_boosts
        else:
            return False, "❌ No views were boosted", 0
    
    async def _boost_with_account(self, client: TelegramClient, account: Dict[str, Any],
                                 channel_link: str, message_ids: List[int], mark_as_read: bool) -> bool:
        """Boost views with a single account"""
        session_name = account["session_name"]
        
        try:
            # Rate limiting
            rate_limiter = await self.get_rate_limiter(session_name)
            await rate_limiter.wait_if_needed()
            await self.global_rate_limiter.wait_if_needed()
            
            async with await self.client_pool.get_client_lock(session_name):
                entity = await client.get_entity(channel_link)
                
                # Boost views
                await client(GetMessagesViewsRequest(
                    peer=entity,
                    id=message_ids,
                    increment=True
                ))
                
                if mark_as_read:
                    try:
                        await client.send_read_acknowledge(entity.id, max_id=max(message_ids))
                    except Exception:
                        pass  # Read acknowledgment is optional
                
                await self.db.log_action(
                    LogType.BOOST,
                    account_id=account["id"],
                    message=f"Boosted {len(message_ids)} messages"
                )
                
                return True
                
        except FloodWaitError as e:
            flood_wait_until = datetime.now() + timedelta(seconds=e.seconds)
            await self.db.update_account_status(account["id"], AccountStatus.FLOOD_WAIT, flood_wait_until)
            return False
            
        except Exception as e:
            logger.debug(f"Boost failed with {account.get('username', account['phone'])}: {e}")
            return False
    
    async def get_channel_messages(self, channel_link: str, limit: int = 10) -> List[int]:
        """Get recent message IDs from a channel"""
        account_pairs = await self.get_next_available_accounts(1)
        
        if not account_pairs:
            return []
        
        client, account = account_pairs[0]
        session_name = account["session_name"]
        
        try:
            async with await self.client_pool.get_client_lock(session_name):
                entity = await client.get_entity(channel_link)
                messages = await client.get_messages(entity, limit=limit)
                return [msg.id for msg in messages if hasattr(msg, 'id') and msg.id]
        except Exception as e:
            logger.error(f"Error getting messages from {channel_link}: {e}")
            return []
    
    async def get_account_health_stats(self) -> Dict[str, Any]:
        """Get comprehensive account health statistics"""
        stats = await self.db.get_account_statistics()
        stats.update({
            "active_clients": len(self.client_pool.active_clients),
            "max_active_clients": self.client_pool.max_active_clients,
            "failed_accounts_count": len(self.failed_accounts),
            "rate_limiters_active": len(self.rate_limiters)
        })
        return stats
    
    async def cleanup(self):
        """Cleanup all resources"""
        logger.info("Shutting down Telethon manager...")
        await self.client_pool.close_all()
        await self.db.close()
        logger.info("Telethon manager cleanup complete")