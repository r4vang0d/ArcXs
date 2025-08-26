"""
Live Stream Monitoring Service
Continuously monitors channels for live streams and auto-joins with all accounts
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from database import DatabaseManager, LogType
from session_manager import TelethonManager

logger = logging.getLogger(__name__)

class LiveMonitorService:
    """Background service for monitoring live streams"""
    
    def __init__(self, db_manager: DatabaseManager, telethon_manager: TelethonManager):
        self.db = db_manager
        self.telethon = telethon_manager
        self.is_running = False
        self.monitor_task = None
        self.check_interval = 15  # Check every 15 seconds for faster detection
        self.joined_calls = set()  # Track which group calls we've already joined
        
    async def start_monitoring(self):
        """Start the live monitoring service"""
        if self.is_running:
            logger.info("Live monitoring service is already running")
            return
        
        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("🔴 Live monitoring service started")
    
    async def stop_monitoring(self):
        """Stop the live monitoring service"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("⏹️ Live monitoring service stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🔄 Starting live monitoring loop...")
        
        while self.is_running:
            try:
                await self._check_all_monitors()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info("🔄 Live monitoring loop stopped")
    
    async def _check_all_monitors(self):
        """Check all active monitors for live streams"""
        try:
            # Get all active monitoring channels
            monitors = await self.db.get_all_active_monitors()
            
            if not monitors:
                return
            
            logger.info(f"🔍 Checking {len(monitors)} monitored channels for live streams...")
            
            for monitor in monitors:
                try:
                    await self._check_monitor(monitor)
                    await asyncio.sleep(1)  # Small delay between checks
                except Exception as e:
                    logger.error(f"Error checking monitor {monitor.get('id')}: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking all monitors: {e}")
    
    async def _check_monitor(self, monitor: Dict[str, Any]):
        """Check a specific monitor for live streams"""
        try:
            channel_link = monitor['channel_link']
            monitor_id = monitor['id']
            
            # Check if channel has live stream
            has_live, group_call_info = await self.telethon.check_channel_for_live_stream(channel_link)
            
            if has_live:
                logger.info(f"🔴 LIVE STREAM DETECTED in {channel_link}!")
                
                # Check if we've already joined this specific group call
                call_id = group_call_info.get('id') if group_call_info else None
                if call_id and call_id in self.joined_calls:
                    logger.debug(f"Already attempted to join group call {call_id}, skipping...")
                    await self.db.update_live_monitor_check(monitor_id, live_detected=True)
                    return
                
                # Get user's preferred account count for live streams
                user_id = monitor['user_id']
                user_account_preference = await self._get_user_live_account_count(user_id)
                
                # Join the live stream with specified or all accounts
                result = await self.telethon.join_live_stream(channel_link, group_call_info, user_account_preference)
                
                # Only mark as attempted if we actually succeeded or if it's permanently invalid
                if call_id and (result['success'] or "invalid" in result.get('message', '').lower()):
                    self.joined_calls.add(call_id)
                    if result['success']:
                        logger.info(f"✅ Marked group call {call_id} as successfully joined")
                    else:
                        logger.info(f"❌ Marked group call {call_id} as invalid - won't retry")
                
                if result['success']:
                    accounts_joined = result['accounts_joined']
                    group_call_joined = result.get('group_call_joined', False)
                    
                    if group_call_joined:
                        logger.info(f"🎤 Successfully joined GROUP CALL with {accounts_joined} accounts - speaking management started!")
                    else:
                        logger.info(f"📺 Successfully joined CHANNEL with {accounts_joined} accounts (no group call access)")
                    
                    # Update database with successful live detection
                    await self.db.update_live_monitor_check(monitor_id, live_detected=True)
                    
                    # Log the successful live join
                    join_type = "group call" if group_call_joined else "channel"
                    await self.db.log_action(
                        LogType.LIVE_JOIN,
                        user_id=monitor['user_id'],
                        message=f"Auto-joined live stream {join_type} in {channel_link} with {accounts_joined} accounts"
                    )
                else:
                    error_msg = result['message']
                    if "invalid" in error_msg.lower():
                        logger.warning(f"⚠️ Group call expired/invalid: {error_msg}")
                    else:
                        logger.error(f"❌ Failed to join live stream: {error_msg}")
            else:
                # Update last checked time (no live detected)
                await self.db.update_live_monitor_check(monitor_id, live_detected=False)
                
        except Exception as e:
            logger.error(f"Error checking monitor for {monitor.get('channel_link')}: {e}")
    
    async def _get_user_live_account_count(self, user_id: int) -> Optional[int]:
        """Get user's preferred account count for live streams"""
        try:
            user = await self.db.get_user(user_id)
            if not user:
                return None
            
            # Parse user settings
            settings_json = user.get("settings", "{}")
            try:
                import json
                settings = json.loads(settings_json) if settings_json else {}
                live_account_count = settings.get("live_account_count")
                
                # Return None if not set (use all accounts) or if it's a valid number
                if live_account_count is None:
                    return None
                elif isinstance(live_account_count, int) and live_account_count > 0:
                    return live_account_count
                else:
                    return None
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid settings JSON for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting user live account count for {user_id}: {e}")
            return None
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        try:
            monitors = await self.db.get_all_active_monitors()
            
            return {
                "is_running": self.is_running,
                "total_monitors": len(monitors),
                "check_interval": self.check_interval,
                "next_check": datetime.now() + timedelta(seconds=self.check_interval) if self.is_running else None
            }
        except Exception as e:
            logger.error(f"Error getting monitor status: {e}")
            return {"is_running": False, "error": str(e)}
    
    async def force_check_channel(self, channel_link: str) -> Dict[str, Any]:
        """Force check a specific channel for live streams (manual trigger)"""
        try:
            has_live = await self.telethon.check_channel_for_live_stream(channel_link)
            
            if has_live:
                result = await self.telethon.join_live_stream(channel_link)
                return {
                    "live_detected": True,
                    "join_result": result
                }
            else:
                return {
                    "live_detected": False,
                    "message": "No live stream detected"
                }
                
        except Exception as e:
            logger.error(f"Error force checking channel {channel_link}: {e}")
            return {"error": str(e)}