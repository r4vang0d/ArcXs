"""
High-Performance PostgreSQL Database Manager for Telegram View Booster Bot
Optimized for handling 2000+ accounts with connection pooling and advanced features
"""
import asyncpg
import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from contextlib import asynccontextmanager

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

class PostgreSQLManager:
    """High-performance PostgreSQL database manager for massive scale"""
    
    def __init__(self, database_url: Optional[str] = None, pool_size: int = 20, max_pool_size: int = 50):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.pool_size = pool_size
        self.max_pool_size = max_pool_size
        self.pool: Optional[asyncpg.Pool] = None
        self._init_lock = asyncio.Lock()
        
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required")
    
    async def init_pool(self):
        """Initialize connection pool"""
        async with self._init_lock:
            if self.pool is None:
                try:
                    self.pool = await asyncpg.create_pool(
                        self.database_url,
                        min_size=self.pool_size,
                        max_size=self.max_pool_size,
                        command_timeout=60,
                        server_settings={
                            'jit': 'off',  # Disable JIT for better performance on small queries
                            'shared_preload_libraries': 'pg_stat_statements'
                        }
                    )
                    await self.init_db()
                    logger.info(f"PostgreSQL pool initialized with {self.pool_size}-{self.max_pool_size} connections")
                except Exception as e:
                    logger.error(f"Failed to create PostgreSQL pool: {e}")
                    raise
    
    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            await self.init_pool()
        
        async with self.pool.acquire() as connection:
            yield connection
    
    async def init_db(self):
        """Initialize database with optimized tables for large scale"""
        async with self.get_connection() as conn:
            # Users table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    premium BOOLEAN DEFAULT FALSE,
                    expiry TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    settings JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            # Accounts table - optimized for massive scale
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    phone TEXT UNIQUE NOT NULL,
                    username TEXT,
                    session_name TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'active',
                    flood_wait_until TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_used TIMESTAMPTZ,
                    failed_attempts INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    priority INTEGER DEFAULT 1
                )
            """)
            
            # Channels table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    channel_link TEXT NOT NULL,
                    channel_id TEXT,
                    title TEXT,
                    member_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_boosted TIMESTAMPTZ,
                    total_boosts INTEGER DEFAULT 0,
                    UNIQUE(user_id, channel_link)
                )
            """)
            
            # Logs table - partitioned for performance
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id SERIAL PRIMARY KEY,
                    log_type TEXT NOT NULL,
                    user_id BIGINT,
                    account_id INTEGER,
                    channel_id INTEGER,
                    message TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            # Account sessions table for lazy loading
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS account_sessions (
                    id SERIAL PRIMARY KEY,
                    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                    session_data BYTEA,
                    last_accessed TIMESTAMPTZ DEFAULT NOW(),
                    access_count INTEGER DEFAULT 0
                )
            """)
            
            # Performance indexes
            await self._create_indexes(conn)
            
            logger.info("PostgreSQL database initialized successfully")
    
    async def _create_indexes(self, conn):
        """Create performance-optimized indexes"""
        indexes = [
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_status ON accounts(status) WHERE is_active = TRUE",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_last_used ON accounts(last_used) WHERE is_active = TRUE",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_phone ON accounts(phone)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_channels_user_id ON channels(user_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_channels_link ON channels(channel_link)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_logs_created_at ON logs(created_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_logs_account_id ON logs(account_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_account_sessions_last_accessed ON account_sessions(last_accessed)"
        ]
        
        for index_query in indexes:
            try:
                await conn.execute(index_query)
            except Exception as e:
                logger.debug(f"Index creation skipped: {e}")
    
    # User management
    async def add_user(self, user_id: int, premium: bool = False, expiry: Optional[datetime] = None) -> bool:
        """Add a new user"""
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO users (id, premium, expiry) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (id) DO UPDATE SET
                        premium = EXCLUDED.premium,
                        expiry = EXCLUDED.expiry
                """, user_id, premium, expiry)
                return True
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT id, premium, expiry, created_at, settings
                    FROM users WHERE id = $1
                """, user_id)
                
                if row:
                    return {
                        "id": row["id"],
                        "premium": row["premium"],
                        "expiry": row["expiry"],
                        "created_at": row["created_at"],
                        "settings": row["settings"]
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    # High-performance account management
    async def add_account(self, phone: str, session_name: str, username: Optional[str] = None, priority: int = 1) -> bool:
        """Add a new Telethon account with priority support"""
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO accounts (phone, username, session_name, priority, status, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (phone) DO UPDATE SET
                        username = EXCLUDED.username,
                        session_name = EXCLUDED.session_name,
                        priority = EXCLUDED.priority,
                        is_active = TRUE
                """, phone, username, session_name, priority, AccountStatus.ACTIVE.value, True)
                
                await self.log_action(LogType.JOIN, message=f"Account {username or phone} added successfully")
                return True
        except Exception as e:
            logger.error(f"Error adding account {phone}: {e}")
            return False
    
    async def get_active_accounts(self, limit: Optional[int] = None, priority_order: bool = True) -> List[Dict[str, Any]]:
        """Get active accounts with intelligent ordering for massive scale"""
        try:
            async with self.get_connection() as conn:
                order_clause = "priority DESC, last_used ASC NULLS FIRST" if priority_order else "last_used ASC NULLS FIRST"
                limit_clause = f"LIMIT {limit}" if limit else ""
                
                rows = await conn.fetch(f"""
                    SELECT id, phone, username, session_name, status, flood_wait_until, 
                           created_at, last_used, failed_attempts, priority
                    FROM accounts 
                    WHERE is_active = TRUE 
                      AND status = $1 
                      AND (flood_wait_until IS NULL OR flood_wait_until < NOW())
                    ORDER BY {order_clause}
                    {limit_clause}
                """, AccountStatus.ACTIVE.value)
                
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting active accounts: {e}")
            return []
    
    async def update_account_status(self, account_id: int, status: AccountStatus, 
                                  flood_wait_until: Optional[datetime] = None) -> bool:
        """Update account status with optimized query"""
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    UPDATE accounts 
                    SET status = $1, flood_wait_until = $2, last_used = NOW()
                    WHERE id = $3
                """, status.value, flood_wait_until, account_id)
                return True
        except Exception as e:
            logger.error(f"Error updating account {account_id} status: {e}")
            return False
    
    async def get_account_batch(self, batch_size: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get accounts in batches for massive scale processing"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT id, phone, username, session_name, status, priority
                    FROM accounts 
                    WHERE is_active = TRUE
                    ORDER BY priority DESC, id
                    LIMIT $1 OFFSET $2
                """, batch_size, offset)
                
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting account batch: {e}")
            return []
    
    # Channel management with consolidation
    async def add_channel(self, user_id: int, channel_link: str, channel_id: Optional[str] = None, 
                         title: Optional[str] = None) -> bool:
        """Add channel with duplicate prevention"""
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO channels (user_id, channel_link, channel_id, title)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, channel_link) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        title = EXCLUDED.title
                """, user_id, channel_link, channel_id, title)
                return True
        except Exception as e:
            logger.error(f"Error adding channel {channel_link} for user {user_id}: {e}")
            return False
    
    async def get_user_channels(self, user_id: int) -> List[Dict[str, Any]]:
        """Get unique channels for a user (consolidated from all accounts)"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
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
                    FROM channels WHERE user_id = $1
                    GROUP BY channel_link, channel_id, title, member_count
                    ORDER BY MIN(created_at) DESC
                """, user_id)
                
                return [
                    {
                        "id": row["id"],
                        "channel_link": row["channel_link"],
                        "channel_id": row["channel_id"],
                        "title": row["title"],
                        "member_count": row["member_count"],
                        "created_at": row["created_at"],
                        "last_boosted": row["last_boosted"],
                        "total_boosts": row["total_boosts"] or 0,
                        "account_count": row["account_count"]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error getting channels for user {user_id}: {e}")
            return []
    
    # High-performance logging
    async def log_action(self, log_type: LogType, user_id: Optional[int] = None, 
                        account_id: Optional[int] = None, channel_id: Optional[int] = None,
                        message: Optional[str] = None, metadata: Optional[Dict] = None):
        """Optimized logging for high-volume operations"""
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO logs (log_type, user_id, account_id, channel_id, message, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, log_type.value, user_id, account_id, channel_id, message, 
                json.dumps(metadata) if metadata else '{}')
        except Exception as e:
            logger.debug(f"Error logging action: {e}")  # Debug level to avoid spam
    
    # Cleanup and maintenance
    async def cleanup_old_logs(self, days_to_keep: int = 30):
        """Clean up old logs to maintain performance"""
        try:
            async with self.get_connection() as conn:
                cutoff_date = datetime.now() - timedelta(days=days_to_keep)
                result = await conn.execute("""
                    DELETE FROM logs WHERE created_at < $1
                """, cutoff_date)
                logger.info(f"Cleaned up logs older than {days_to_keep} days")
        except Exception as e:
            logger.error(f"Error cleaning up logs: {e}")
    
    async def get_account_statistics(self) -> Dict[str, int]:
        """Get comprehensive account statistics"""
        try:
            async with self.get_connection() as conn:
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_accounts,
                        COUNT(*) FILTER (WHERE status = 'active' AND is_active = TRUE) as active_accounts,
                        COUNT(*) FILTER (WHERE status = 'banned') as banned_accounts,
                        COUNT(*) FILTER (WHERE status = 'floodwait') as flood_wait_accounts,
                        COUNT(*) FILTER (WHERE is_active = FALSE) as inactive_accounts
                    FROM accounts
                """)
                
                return dict(stats) if stats else {}
        except Exception as e:
            logger.error(f"Error getting account statistics: {e}")
            return {}
    
    async def close(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")