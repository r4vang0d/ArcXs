"""
Database management for the Telegram View Booster Bot
Uses SQLite for local data storage
"""
import aiosqlite
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

class AccountStatus(Enum):
    ACTIVE = "active"
    BANNED = "banned" 
    FLOOD_WAIT = "floodwait"
    INACTIVE = "inactive"

class LogType(Enum):
    JOIN = "join"
    BOOST = "boost"
    ERROR = "error"
    BAN = "ban"
    FLOOD_WAIT = "flood_wait"

class DatabaseManager:
    """Manages SQLite database operations"""
    
    def __init__(self, db_path: str = "bot_data.db"):
        self.db_path = db_path
        self._operation_lock = asyncio.Lock()
        self._connection = None
    
    async def init_db(self):
        """Initialize database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    premium BOOLEAN DEFAULT FALSE,
                    expiry DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    settings TEXT DEFAULT '{}'
                )
            """)
            
            # Accounts table (Telethon sessions)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    username TEXT,
                    session_name TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'active',
                    flood_wait_until DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    failed_attempts INTEGER DEFAULT 0
                )
            """)
            
            # Add username column if it doesn't exist
            try:
                await db.execute("ALTER TABLE accounts ADD COLUMN username TEXT")
                await db.commit()
            except Exception:
                pass  # Column already exists
            
            # Channels table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_link TEXT NOT NULL,
                    channel_id TEXT,
                    title TEXT,
                    member_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_boosted DATETIME,
                    total_boosts INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    account_id INTEGER,
                    channel_id INTEGER,
                    user_id INTEGER,
                    message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts (id),
                    FOREIGN KEY (channel_id) REFERENCES channels (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Premium user settings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS premium_settings (
                    user_id INTEGER PRIMARY KEY,
                    max_channels INTEGER DEFAULT 1,
                    max_daily_boosts INTEGER DEFAULT 100,
                    custom_limits TEXT,
                    upgraded_by INTEGER,
                    upgrade_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (upgraded_by) REFERENCES users (id)
                )
            """)
            
            # Channel whitelist/blacklist table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS channel_control (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_link TEXT UNIQUE NOT NULL,
                    channel_id TEXT,
                    status TEXT DEFAULT 'allowed',
                    reason TEXT,
                    added_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (added_by) REFERENCES users (id)
                )
            """)
            
            # Live monitoring table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS live_monitoring (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_link TEXT NOT NULL,
                    channel_id TEXT,
                    title TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    last_checked DATETIME,
                    live_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create indexes for performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_premium ON users (premium)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts (status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_channels_user ON channels (user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_type ON logs (type)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON logs (created_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_premium_settings_user ON premium_settings (user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_channel_control_status ON channel_control (status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_live_monitoring_user ON live_monitoring (user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_live_monitoring_active ON live_monitoring (active)")
            
            await db.commit()
            logger.info("Database initialized successfully")
    
    async def _ensure_connection(self):
        """Ensure we have a valid database connection"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA synchronous=NORMAL") 
            await self._connection.execute("PRAGMA cache_size=1000")
            await self._connection.execute("PRAGMA temp_store=MEMORY")
        return self._connection
    
    async def _execute_with_lock(self, query: str, params=None):
        """Execute a query with proper locking"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            if params:
                return await connection.execute(query, params)
            else:
                return await connection.execute(query)
    
    async def _commit_with_lock(self):
        """Commit with proper locking"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            await connection.commit()
    
    # User management
    async def add_user(self, user_id: int, premium: bool = False, expiry: Optional[datetime] = None) -> bool:
        """Add or update a user (preserves existing settings)"""
        try:
            # Check if user exists first
            existing_user = await self.get_user(user_id)
            if existing_user:
                # User exists, only update premium and expiry, preserve settings
                await self._execute_with_lock("""
                    UPDATE users SET premium = ?, expiry = ? WHERE id = ?
                """, (premium, expiry, user_id))
            else:
                # New user, insert with default settings
                await self._execute_with_lock("""
                    INSERT INTO users (id, premium, expiry, settings)
                    VALUES (?, ?, ?, '{}')
                """, (user_id, premium, expiry))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("""
                    SELECT id, premium, expiry, created_at, settings
                    FROM users WHERE id = ?
                """, (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "premium": bool(row[1]),
                            "expiry": row[2],
                            "created_at": row[3],
                            "settings": row[4]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def is_premium_user(self, user_id: int) -> bool:
        """Check if user has premium access"""
        user = await self.get_user(user_id)
        if not user or not user["premium"]:
            return False
        
        if user["expiry"]:
            expiry = datetime.fromisoformat(user["expiry"])
            return expiry > datetime.now()
        
        return True
    
    # Account management
    async def add_account(self, phone: str, session_name: str, username: Optional[str] = None) -> bool:
        """Add a new Telethon account"""
        try:
            await self._execute_with_lock("""
                INSERT INTO accounts (phone, username, session_name, status)
                VALUES (?, ?, ?, ?)
            """, (phone, username, session_name, AccountStatus.ACTIVE.value))
            await self._commit_with_lock()
            display_name = username if username else phone
            await self.log_action(LogType.JOIN, message=f"Account {display_name} added successfully")
            return True
        except Exception as e:
            logger.error(f"Error adding account {phone}: {e}")
            return False
    
    async def remove_account(self, phone: str) -> bool:
        """Remove an account"""
        try:
            await self._execute_with_lock("DELETE FROM accounts WHERE phone = ?", (phone,))
            await self._commit_with_lock()
            await self.log_action(LogType.JOIN, message=f"Account {phone} removed")
            return True
        except Exception as e:
            logger.error(f"Error removing account {phone}: {e}")
            return False
    
    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts with their status"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("""
                    SELECT id, phone, username, session_name, status, flood_wait_until, 
                           created_at, last_used, failed_attempts
                    FROM accounts ORDER BY created_at
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "phone": row[1],
                            "username": row[2],
                            "session_name": row[3],
                            "status": row[4],
                            "flood_wait_until": row[5],
                            "created_at": row[6],
                            "last_used": row[7],
                            "failed_attempts": row[8]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
    
    async def get_active_accounts(self) -> List[Dict[str, Any]]:
        """Get only active accounts that can be used"""
        try:
            now = datetime.now()
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("""
                    SELECT id, phone, username, session_name, status, flood_wait_until,
                           created_at, last_used, failed_attempts
                    FROM accounts 
                    WHERE status = ? AND (flood_wait_until IS NULL OR flood_wait_until < ?)
                    ORDER BY last_used ASC NULLS FIRST
                """, (AccountStatus.ACTIVE.value, now)) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "phone": row[1],
                            "username": row[2],
                            "session_name": row[3],
                            "status": row[4],
                            "flood_wait_until": row[5],
                            "created_at": row[6],
                            "last_used": row[7],
                            "failed_attempts": row[8]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting active accounts: {e}")
            return []
    
    async def update_account_status(self, account_id: int, status: AccountStatus, 
                                  flood_wait_until: Optional[datetime] = None) -> bool:
        """Update account status"""
        try:
            await self._execute_with_lock("""
                UPDATE accounts 
                SET status = ?, flood_wait_until = ?, last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status.value, flood_wait_until, account_id))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error updating account {account_id} status: {e}")
            return False
    
    async def increment_failed_attempts(self, account_id: int) -> bool:
        """Increment failed attempts counter for an account"""
        try:
            await self._execute_with_lock("""
                UPDATE accounts 
                SET failed_attempts = failed_attempts + 1, last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (account_id,))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error incrementing failed attempts for account {account_id}: {e}")
            return False
    
    # Channel management
    async def add_channel(self, user_id: int, channel_link: str, channel_id: Optional[str] = None, title: Optional[str] = None) -> bool:
        """Add a channel for a user"""
        try:
            await self._execute_with_lock("""
                INSERT INTO channels (user_id, channel_link, channel_id, title)
                VALUES (?, ?, ?, ?)
            """, (user_id, channel_link, channel_id, title))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error adding channel {channel_link} for user {user_id}: {e}")
            return False
    
    async def get_user_channels(self, user_id: int) -> List[Dict[str, Any]]:
        """Get unique channels for a user (consolidated from all accounts)"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("""
                    SELECT 
                        MIN(id) as id,
                        channel_link, 
                        channel_id, 
                        title, 
                        member_count,
                        MIN(created_at) as created_at, 
                        MAX(last_boosted) as last_boosted, 
                        SUM(total_boosts) as total_boosts,
                        COUNT(*) as account_count
                    FROM channels WHERE user_id = ?
                    GROUP BY channel_link, channel_id
                    ORDER BY MIN(created_at) DESC
                """, (user_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "channel_link": row[1],
                            "channel_id": row[2],
                            "title": row[3],
                            "member_count": row[4],
                            "created_at": row[5],
                            "last_boosted": row[6],
                            "total_boosts": row[7] or 0,
                            "account_count": row[8]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting channels for user {user_id}: {e}")
            return []
    
    async def get_channel_accounts(self, user_id: int, channel_link: str) -> List[Dict[str, Any]]:
        """Get all accounts that joined a specific channel"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("""
                    SELECT c.*, a.phone, a.username, a.session_name, a.status
                    FROM channels c
                    JOIN accounts a ON a.id = c.user_id OR a.phone IN (
                        SELECT phone FROM accounts WHERE id = c.user_id
                    )
                    WHERE c.user_id = ? AND c.channel_link = ?
                """, (user_id, channel_link)) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "channel_id": row[2],
                            "phone": row[7],
                            "username": row[8],
                            "session_name": row[9],
                            "status": row[10]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting channel accounts: {e}")
            return []
    
    async def update_channel_boost(self, channel_id: int, boost_count: int = 1) -> bool:
        """Update channel boost statistics"""
        try:
            await self._execute_with_lock("""
                UPDATE channels 
                SET last_boosted = CURRENT_TIMESTAMP, 
                    total_boosts = total_boosts + ?
                WHERE id = ?
            """, (boost_count, channel_id))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error updating channel {channel_id} boost: {e}")
            return False
    
    async def remove_channel(self, channel_id: int, user_id: int) -> bool:
        """Remove a channel (only by the owner)"""
        try:
            await self._execute_with_lock("""
                DELETE FROM channels WHERE id = ? AND user_id = ?
            """, (channel_id, user_id))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error removing channel {channel_id}: {e}")
            return False
    
    # Logging
    async def log_action(self, log_type: LogType, account_id: Optional[int] = None, 
                        channel_id: Optional[int] = None, user_id: Optional[int] = None, message: Optional[str] = None) -> bool:
        """Log an action to the database"""
        try:
            await self._execute_with_lock("""
                INSERT INTO logs (type, account_id, channel_id, user_id, message)
                VALUES (?, ?, ?, ?, ?)
            """, (log_type.value, account_id, channel_id, user_id, message))
            await self._commit_with_lock()
            return True
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return False
    
    async def get_logs(self, limit: int = 100, log_type: Optional[LogType] = None) -> List[Dict[str, Any]]:
        """Get recent logs"""
        try:
            query = """
                SELECT l.id, l.type, l.message, l.created_at,
                       a.phone as account_phone,
                       a.username as account_username,
                       c.channel_link,
                       l.user_id
                FROM logs l
                LEFT JOIN accounts a ON l.account_id = a.id
                LEFT JOIN channels c ON l.channel_id = c.id
            """
            params = []
            
            if log_type:
                query += " WHERE l.type = ?"
                params.append(log_type.value)
            
            query += " ORDER BY l.created_at DESC LIMIT ?"
            params.append(limit)
            
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "type": row[1],
                            "message": row[2],
                            "created_at": row[3],
                            "account_phone": row[4],
                            "account_username": row[5],
                            "channel_link": row[6],
                            "user_id": row[7]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return []
    
    async def get_user_count(self) -> int:
        """Get total user count"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                async with connection.execute("SELECT COUNT(*) FROM users") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting user count: {e}")
            return 0
    
    # Premium management methods removed for personal use
    
    # === Channel Control Methods ===
    
    async def add_channel_to_whitelist(self, channel_link: str, admin_id: int, reason: Optional[str] = None):
        """Add channel to whitelist"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            await connection.execute("""
                INSERT OR REPLACE INTO channel_control 
                (channel_link, status, reason, added_by)
                VALUES (?, 'whitelisted', ?, ?)
            """, (channel_link, reason, admin_id))
            await connection.commit()
            logger.info(f"Channel {channel_link} whitelisted by admin {admin_id}")
    
    async def add_channel_to_blacklist(self, channel_link: str, admin_id: int, reason: Optional[str] = None):
        """Add channel to blacklist"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            await connection.execute("""
                INSERT OR REPLACE INTO channel_control 
                (channel_link, status, reason, added_by)
                VALUES (?, 'blacklisted', ?, ?)
            """, (channel_link, reason, admin_id))
            await connection.commit()
            logger.info(f"Channel {channel_link} blacklisted by admin {admin_id}")
    
    async def get_channel_control_lists(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get whitelist and blacklist"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            cursor = await connection.execute("""
                SELECT channel_link, status, reason, added_by, created_at
                FROM channel_control
                ORDER BY created_at DESC
            """)
            rows = await cursor.fetchall()
            
            lists = {"whitelisted": [], "blacklisted": []}
            for row in rows:
                row_dict = dict(row)
                if row_dict["status"] in lists:
                    lists[row_dict["status"]].append(row_dict)
            
            return lists
    
    async def remove_from_channel_control(self, channel_link: str):
        """Remove channel from control lists"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            await connection.execute(
                "DELETE FROM channel_control WHERE channel_link = ?",
                (channel_link,)
            )
            await connection.commit()
            logger.info(f"Channel {channel_link} removed from control lists")
    
    async def is_channel_allowed(self, channel_link: str) -> bool:
        """Check if channel is allowed (not blacklisted)"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            cursor = await connection.execute(
                "SELECT status FROM channel_control WHERE channel_link = ?",
                (channel_link,)
            )
            row = await cursor.fetchone()
            
            if row:
                return row[0] != "blacklisted"
            return True  # Allow by default if not in control list
    
    # Live monitoring methods
    async def add_live_monitor(self, user_id: int, channel_link: str, title: str = None) -> bool:
        """Add a channel to live monitoring"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                await connection.execute("""
                    INSERT OR REPLACE INTO live_monitoring 
                    (user_id, channel_link, title, active, created_at)
                    VALUES (?, ?, ?, TRUE, CURRENT_TIMESTAMP)
                """, (user_id, channel_link, title))
                await connection.commit()
                logger.info(f"Added live monitor for channel {channel_link} by user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding live monitor: {e}")
            return False
    
    async def get_live_monitors(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all live monitoring channels for a user"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            cursor = await connection.execute("""
                SELECT id, channel_link, title, active, last_checked, live_count, created_at
                FROM live_monitoring
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_all_active_monitors(self) -> List[Dict[str, Any]]:
        """Get all active live monitoring channels"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            cursor = await connection.execute("""
                SELECT id, user_id, channel_link, title, last_checked, live_count
                FROM live_monitoring
                WHERE active = TRUE
                ORDER BY last_checked ASC
            """)
            rows = await cursor.fetchall()
            
            # Convert rows to dictionaries properly
            result = []
            for row in rows:
                result.append({
                    "id": row[0],
                    "user_id": row[1], 
                    "channel_link": row[2],
                    "title": row[3],
                    "last_checked": row[4],
                    "live_count": row[5]
                })
            return result
    
    async def update_live_monitor_check(self, monitor_id: int, live_detected: bool = False):
        """Update last checked time and live count"""
        async with self._operation_lock:
            connection = await self._ensure_connection()
            if live_detected:
                await connection.execute("""
                    UPDATE live_monitoring 
                    SET last_checked = CURRENT_TIMESTAMP, live_count = live_count + 1
                    WHERE id = ?
                """, (monitor_id,))
            else:
                await connection.execute("""
                    UPDATE live_monitoring 
                    SET last_checked = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (monitor_id,))
            await connection.commit()
    
    async def remove_live_monitor(self, user_id: int, monitor_id: int) -> bool:
        """Remove a live monitoring channel"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                await connection.execute("""
                    DELETE FROM live_monitoring 
                    WHERE id = ? AND user_id = ?
                """, (monitor_id, user_id))
                await connection.commit()
                logger.info(f"Removed live monitor {monitor_id} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing live monitor: {e}")
            return False
    
    async def toggle_live_monitor(self, user_id: int, monitor_id: int, active: bool) -> bool:
        """Toggle live monitoring on/off for a channel"""
        try:
            async with self._operation_lock:
                connection = await self._ensure_connection()
                await connection.execute("""
                    UPDATE live_monitoring 
                    SET active = ?
                    WHERE id = ? AND user_id = ?
                """, (active, monitor_id, user_id))
                await connection.commit()
                return True
        except Exception as e:
            logger.error(f"Error toggling live monitor: {e}")
            return False
    
    async def close(self):
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None
