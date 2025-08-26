"""
Advanced Retry Queue Manager for Telegram Live Calls
Implements persistent retry strategy with queue system as per guide
"""
import asyncio
import logging
import time
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass
from enum import Enum
import random

logger = logging.getLogger(__name__)

class RetryTaskType(Enum):
    JOIN_GROUP_CALL = "join_group_call"
    RAISE_HAND = "raise_hand"
    RECONNECT = "reconnect"

@dataclass
class RetryTask:
    """Represents a retry task in the queue"""
    session_name: str
    task_type: RetryTaskType
    group_call_info: Dict[str, Any]
    channel_link: str
    attempt_count: int = 0
    last_attempt: float = 0
    next_retry: float = 0
    max_retries: int = 50  # Per guide: keep retrying up to 50 times
    client: Any = None
    entity: Any = None

class RetryQueueManager:
    """
    Master orchestrator for handling all retry operations
    Implements queue system that never skips failures
    """
    
    def __init__(self, session_manager):
        self.session_manager = session_manager
        self.retry_queues: Dict[str, asyncio.Queue] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.failed_accounts: Set[str] = set()
        self.permanent_bans: Set[str] = set()
        self.is_running = False
        
        # Retry timing configuration (exponential backoff as per guide)
        self.retry_delays = [2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]  # Up to 1 hour
        
    async def start(self):
        """Start the retry queue manager"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("🚀 Retry Queue Manager started - will never skip failures")
        
    async def stop(self):
        """Stop the retry queue manager"""
        self.is_running = False
        
        # Cancel all active retry tasks
        for task_name, task in self.active_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        self.active_tasks.clear()
        logger.info("⏹️ Retry Queue Manager stopped")
        
    def add_retry_task(self, task: RetryTask):
        """Add a retry task to the queue (never skip)"""
        if task.session_name in self.permanent_bans:
            logger.info(f"⛔ Account {task.session_name} permanently banned, skipping retry")
            return
            
        # Create queue for this account if it doesn't exist
        if task.session_name not in self.retry_queues:
            self.retry_queues[task.session_name] = asyncio.Queue()
            
        # Add task to queue
        try:
            self.retry_queues[task.session_name].put_nowait(task)
            logger.info(f"📝 Added retry task for {task.session_name}: {task.task_type.value}")
            
            # Start worker for this account if not already running
            if task.session_name not in self.active_tasks or self.active_tasks[task.session_name].done():
                self.active_tasks[task.session_name] = asyncio.create_task(
                    self._process_retry_queue(task.session_name)
                )
                
        except asyncio.QueueFull:
            logger.warning(f"⚠️ Retry queue full for {task.session_name}")
            
    async def _process_retry_queue(self, session_name: str):
        """Process retry queue for a specific account (background worker)"""
        logger.info(f"🔄 Starting retry worker for {session_name}")
        
        queue = self.retry_queues[session_name]
        
        while self.is_running and session_name not in self.permanent_bans:
            try:
                # Get next task from queue
                task = await asyncio.wait_for(queue.get(), timeout=60)
                
                # Check if it's time to retry
                current_time = time.time()
                if current_time < task.next_retry:
                    wait_time = task.next_retry - current_time
                    logger.info(f"⏰ Waiting {wait_time:.1f}s before retry for {session_name}")
                    await asyncio.sleep(wait_time)
                
                # Attempt the retry
                success = await self._execute_retry_task(task)
                
                if success:
                    logger.info(f"✅ Retry successful for {session_name}: {task.task_type.value}")
                else:
                    # Failed - calculate next retry time with exponential backoff
                    task.attempt_count += 1
                    task.last_attempt = time.time()
                    
                    if task.attempt_count >= task.max_retries:
                        logger.error(f"❌ Max retries ({task.max_retries}) reached for {session_name}")
                        # Alert admin but continue trying (as per guide)
                        await self._alert_admin_max_retries(session_name, task)
                        
                    # Calculate next retry delay (exponential backoff)
                    delay_index = min(task.attempt_count - 1, len(self.retry_delays) - 1)
                    base_delay = self.retry_delays[delay_index]
                    
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0.5, 1.5)
                    actual_delay = base_delay * jitter
                    
                    task.next_retry = time.time() + actual_delay
                    
                    logger.info(f"🔄 Retry {task.attempt_count} failed for {session_name}, next attempt in {actual_delay:.1f}s")
                    
                    # Put task back in queue for retry
                    queue.put_nowait(task)
                
                queue.task_done()
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error in retry worker for {session_name}: {e}")
                await asyncio.sleep(5)
                
        logger.info(f"🔄 Retry worker stopped for {session_name}")
        
    async def _execute_retry_task(self, task: RetryTask) -> bool:
        """Execute a specific retry task"""
        try:
            if task.task_type == RetryTaskType.JOIN_GROUP_CALL:
                return await self._retry_join_group_call(task)
            elif task.task_type == RetryTaskType.RAISE_HAND:
                return await self._retry_raise_hand(task)
            elif task.task_type == RetryTaskType.RECONNECT:
                return await self._retry_reconnect(task)
            else:
                logger.error(f"Unknown retry task type: {task.task_type}")
                return False
                
        except Exception as e:
            error_str = str(e).lower()
            
            # Handle FloodWait specially (as per guide)
            if "floodwait" in error_str:
                wait_time = self._extract_flood_wait_time(str(e))
                logger.warning(f"⚠️ FloodWait for {task.session_name}: {wait_time}s")
                task.next_retry = time.time() + wait_time
                return False
                
            # Check for permanent bans
            if "banned" in error_str or "deleted" in error_str:
                logger.error(f"⛔ Account {task.session_name} permanently banned/deleted")
                self.permanent_bans.add(task.session_name)
                await self._alert_admin_permanent_ban(task.session_name)
                return False
                
            logger.error(f"Error executing retry task for {task.session_name}: {e}")
            return False
            
    async def _retry_join_group_call(self, task: RetryTask) -> bool:
        """Retry joining group call"""
        try:
            # Get fresh group call info (as per guide)
            fresh_has_live, fresh_group_call_info = await self.session_manager.check_channel_for_live_stream(task.channel_link)
            
            if not fresh_has_live or not fresh_group_call_info:
                logger.info(f"🔴 Live stream ended for {task.session_name}, stopping retries")
                return True  # Live ended, consider successful exit
                
            # Update task with fresh info
            task.group_call_info = fresh_group_call_info
            
            # Attempt join with fresh data
            result = await self.session_manager._try_alternative_join_methods(
                task.client, task.session_name, 
                self.session_manager._create_group_call_input(fresh_group_call_info),
                fresh_group_call_info, task.entity, await task.client.get_me()
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in retry join for {task.session_name}: {e}")
            return False
            
    async def _retry_raise_hand(self, task: RetryTask) -> bool:
        """Retry raising hand for speaking permission"""
        try:
            success = await self.session_manager._request_to_speak(
                task.client, task.session_name,
                self.session_manager._create_group_call_input(task.group_call_info)
            )
            return success
            
        except Exception as e:
            logger.error(f"Error in retry raise hand for {task.session_name}: {e}")
            return False
            
    async def _retry_reconnect(self, task: RetryTask) -> bool:
        """Retry reconnection to group call"""
        try:
            success = await self.session_manager._auto_rejoin_group_call(
                task.client, task.session_name,
                self.session_manager._create_group_call_input(task.group_call_info),
                task.group_call_info, task.entity
            )
            return success
            
        except Exception as e:
            logger.error(f"Error in retry reconnect for {task.session_name}: {e}")
            return False
            
    def _extract_flood_wait_time(self, error_message: str) -> int:
        """Extract wait time from FloodWait error"""
        try:
            # Extract number from error message
            import re
            match = re.search(r'(\d+)', error_message)
            if match:
                return int(match.group(1))
        except:
            pass
        return 300  # Default 5 minutes if can't parse
        
    async def _alert_admin_max_retries(self, session_name: str, task: RetryTask):
        """Alert admin about max retries reached"""
        logger.error(f"🚨 ADMIN ALERT: Max retries reached for {session_name} - {task.task_type.value}")
        # Could send Telegram message to admin here
        
    async def _alert_admin_permanent_ban(self, session_name: str):
        """Alert admin about permanent ban"""
        logger.error(f"🚨 ADMIN ALERT: Account {session_name} permanently banned")
        # Could send Telegram message to admin here
        
    def get_status(self) -> Dict[str, Any]:
        """Get current status of retry queues"""
        return {
            "active_workers": len(self.active_tasks),
            "failed_accounts": len(self.failed_accounts),
            "permanent_bans": len(self.permanent_bans),
            "queue_sizes": {name: queue.qsize() for name, queue in self.retry_queues.items()}
        }