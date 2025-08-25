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
                    session_name TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'active',
                    flood_wait_until DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    failed_attempts INTEGER DEFAULT 0
                )
            """)
            
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
            
            # Create indexes for performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_premium ON users (premium)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts (status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_channels_user ON channels (user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_type ON logs (type)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON logs (created_at)")
            
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
        """Add or update a user"""
        try:
            await self._execute_with_lock("""
                INSERT OR REPLACE INTO users (id, premium, expiry)
                VALUES (?, ?, ?)
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
    async def add_account(self, phone: str, session_name: str) -> bool:
        """Add a new Telethon account"""
        try:
            await self._execute_with_lock("""
                INSERT INTO accounts (phone, session_name, status)
                VALUES (?, ?, ?)
            """, (phone, session_name, AccountStatus.ACTIVE.value))
            await self._commit_with_lock()
            await self.log_action(LogType.JOIN, message=f"Account {phone} added successfully")
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
                    SELECT id, phone, session_name, status, flood_wait_until, 
                           created_at, last_used, failed_attempts
                    FROM accounts ORDER BY created_at
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "phone": row[1], 
                            "session_name": row[2],
                            "status": row[3],
                            "flood_wait_until": row[4],
                            "created_at": row[5],
                            "last_used": row[6],
                            "failed_attempts": row[7]
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
                    SELECT id, phone, session_name, status, flood_wait_until,
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
                            "session_name": row[2],
                            "status": row[3],
                            "flood_wait_until": row[4],
                            "created_at": row[5],
                            "last_used": row[6],
                            "failed_attempts": row[7]
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
            async with await self.get_connection() as db:
                await db.execute("""
                    UPDATE accounts 
                    SET status = ?, flood_wait_until = ?, last_used = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status.value, flood_wait_until, account_id))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating account {account_id} status: {e}")
            return False
    
    async def increment_failed_attempts(self, account_id: int) -> bool:
        """Increment failed attempts counter for an account"""
        try:
            async with await self.get_connection() as db:
                await db.execute("""
                    UPDATE accounts 
                    SET failed_attempts = failed_attempts + 1, last_used = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (account_id,))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error incrementing failed attempts for account {account_id}: {e}")
            return False
    
    # Channel management
    async def add_channel(self, user_id: int, channel_link: str, channel_id: Optional[str] = None, title: Optional[str] = None) -> bool:
        """Add a channel for a user"""
        try:
            async with await self.get_connection() as db:
                await db.execute("""
                    INSERT INTO channels (user_id, channel_link, channel_id, title)
                    VALUES (?, ?, ?, ?)
                """, (user_id, channel_link, channel_id, title))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding channel {channel_link} for user {user_id}: {e}")
            return False
    
    async def get_user_channels(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all channels for a user"""
        try:
            async with await self.get_connection() as db:
                async with db.execute("""
                    SELECT id, channel_link, channel_id, title, member_count,
                           created_at, last_boosted, total_boosts
                    FROM channels WHERE user_id = ?
                    ORDER BY created_at DESC
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
                            "total_boosts": row[7]
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Error getting channels for user {user_id}: {e}")
            return []
    
    async def update_channel_boost(self, channel_id: int, boost_count: int = 1) -> bool:
        """Update channel boost statistics"""
        try:
            async with await self.get_connection() as db:
                await db.execute("""
                    UPDATE channels 
                    SET last_boosted = CURRENT_TIMESTAMP, 
                        total_boosts = total_boosts + ?
                    WHERE id = ?
                """, (boost_count, channel_id))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating channel {channel_id} boost: {e}")
            return False
    
    async def remove_channel(self, channel_id: int, user_id: int) -> bool:
        """Remove a channel (only by the owner)"""
        try:
            async with await self.get_connection() as db:
                await db.execute("""
                    DELETE FROM channels WHERE id = ? AND user_id = ?
                """, (channel_id, user_id))
                await db.commit()
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
            
            async with await self.get_connection() as db:
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [
                        {
                            "id": row[0],
                            "type": row[1],
                            "message": row[2],
                            "created_at": row[3],
                            "account_phone": row[4],
                            "channel_link": row[5],
                            "user_id": row[6]
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
