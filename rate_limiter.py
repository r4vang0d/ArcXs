"""
Advanced rate limiter for Telegram operations
Prevents flood errors and manages API call limits
"""
import asyncio
import time
from typing import Dict, List
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Advanced rate limiter with multiple strategies"""
    
    def __init__(self):
        # Per-account rate limiting
        self.account_calls = defaultdict(deque)  # account_id -> deque of timestamps
        self.account_locks = defaultdict(asyncio.Lock)
        
        # Global rate limiting
        self.global_calls = deque()
        self.global_lock = asyncio.Lock()
        
        # Flood wait tracking
        self.flood_waits = {}  # account_id -> (until_time, seconds)
        
        # Rate limits (calls per minute)
        self.ACCOUNT_LIMIT = 20  # per account per minute
        self.GLOBAL_LIMIT = 100   # global per minute
        
        # Delays
        self.MIN_DELAY = 1.0
        self.MAX_DELAY = 3.0
        self.FLOOD_WAIT_BUFFER = 5  # Extra seconds to wait after flood wait
    
    async def wait_for_account(self, account_id: str) -> bool:
        """Wait for account to be available for API calls"""
        async with self.account_locks[account_id]:
            current_time = time.time()
            
            # Check flood wait
            if account_id in self.flood_waits:
                until_time, seconds = self.flood_waits[account_id]
                if current_time < until_time:
                    remaining = until_time - current_time
                    logger.warning(f"Account {account_id} in flood wait for {remaining:.1f}s")
                    return False
                else:
                    # Flood wait expired
                    del self.flood_waits[account_id]
            
            # Clean old calls (older than 60 seconds)
            calls = self.account_calls[account_id]
            while calls and calls[0] < current_time - 60:
                calls.popleft()
            
            # Check rate limit
            if len(calls) >= self.ACCOUNT_LIMIT:
                sleep_time = 60 - (current_time - calls[0])
                if sleep_time > 0:
                    logger.info(f"Account {account_id} rate limited, waiting {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)
                    return await self.wait_for_account(account_id)
            
            # Add current call
            calls.append(current_time)
            return True
    
    async def wait_global(self) -> bool:
        """Wait for global rate limit"""
        async with self.global_lock:
            current_time = time.time()
            
            # Clean old calls
            while self.global_calls and self.global_calls[0] < current_time - 60:
                self.global_calls.popleft()
            
            # Check global limit
            if len(self.global_calls) >= self.GLOBAL_LIMIT:
                sleep_time = 60 - (current_time - self.global_calls[0])
                if sleep_time > 0:
                    logger.info(f"Global rate limit reached, waiting {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)
                    return await self.wait_global()
            
            # Add current call
            self.global_calls.append(current_time)
            return True
    
    async def execute_with_rate_limit(self, coro, account_id: str = None):
        """Execute coroutine with rate limiting"""
        try:
            # Wait for global rate limit
            await self.wait_global()
            
            # Wait for account rate limit if specified
            if account_id:
                if not await self.wait_for_account(account_id):
                    raise Exception(f"Account {account_id} is in flood wait")
            
            # Add small delay between calls
            import random
            delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY)
            await asyncio.sleep(delay)
            
            # Execute the coroutine
            return await coro
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Handle flood wait errors
            if "flood" in error_msg and "wait" in error_msg:
                try:
                    # Extract wait time from error message
                    import re
                    match = re.search(r'(\d+)', error_msg)
                    wait_seconds = int(match.group(1)) if match else 300
                    
                    if account_id:
                        until_time = time.time() + wait_seconds + self.FLOOD_WAIT_BUFFER
                        self.flood_waits[account_id] = (until_time, wait_seconds)
                        logger.error(f"Flood wait for account {account_id}: {wait_seconds}s")
                    
                except Exception:
                    # Fallback flood wait
                    if account_id:
                        until_time = time.time() + 300 + self.FLOOD_WAIT_BUFFER
                        self.flood_waits[account_id] = (until_time, 300)
            
            raise e
    
    def get_account_status(self, account_id: str) -> Dict:
        """Get account rate limit status"""
        current_time = time.time()
        
        # Check flood wait
        if account_id in self.flood_waits:
            until_time, seconds = self.flood_waits[account_id]
            if current_time < until_time:
                return {
                    "status": "flood_wait",
                    "remaining_time": until_time - current_time,
                    "original_wait": seconds
                }
        
        # Check rate limit
        calls = self.account_calls[account_id]
        recent_calls = len([c for c in calls if c > current_time - 60])
        
        return {
            "status": "available" if recent_calls < self.ACCOUNT_LIMIT else "rate_limited",
            "calls_per_minute": recent_calls,
            "limit": self.ACCOUNT_LIMIT
        }

# Global rate limiter instance
rate_limiter = RateLimiter()