# Overview

This is a Telegram View Booster Bot built with Python using Aiogram and Telethon. The bot allows users to manage Telegram channels and boost message views through automated account operations. It features a dual-interface system with separate admin and user panels, account management capabilities, and comprehensive logging.

The bot uses Aiogram for the main bot interface and Telethon for Telegram client operations like joining channels and boosting views. **Recent Update**: Now shows unique channels (consolidated view) and automatically uses all available accounts in rotation for view boosting.

# Recent Changes

## August 26, 2025
- **Comprehensive State Management Fix**: Resolved all state clearing and callback routing issues causing empty state errors
- **Emoji Reaction System Fix**: Fixed "Invalid reaction provided" error by updating emoji format to proper Unicode characters
- **Enhanced Error Recovery**: Added fallback emoji reaction system and comprehensive error handling
- **Database Method Addition**: Added missing get_active_account_count method to prevent crashes
- **Session Recovery System**: Implemented robust state validation and restoration for interrupted sessions
- **Improved User Experience**: Added clear error messages and navigation for expired sessions
- **Production Stability**: Removed debug logging and optimized state persistence across all operations

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework Architecture
- **Bot Framework**: Aiogram for main bot operations and user interface
- **Telegram Client**: Telethon for low-level Telegram operations (joining channels, boosting views)
- **State Management**: FSM (Finite State Machine) using Aiogram's built-in storage
- **Configuration**: Environment-based configuration with python-dotenv

## Database Design
- **Database Engine**: SQLite with aiosqlite for async operations
- **Connection Management**: Connection pooling with async locks for thread safety
- **Schema**: Relational design with tables for users, accounts, channels, logs, and failed operations
- **Data Models**: Enum-based status tracking for accounts (ACTIVE, BANNED, FLOOD_WAIT, INACTIVE)

## Authentication & Authorization
- **Admin Access**: Environment variable-based admin ID validation
- **User Tiers**: Free vs Premium user classification with feature restrictions
- **Session Management**: Telethon session files stored in dedicated sessions directory

## Account Management Architecture
- **Multi-Account Support**: Multiple Telegram accounts managed through Telethon clients
- **Session Storage**: File-based session persistence for Telegram accounts
- **Health Monitoring**: Real-time account status tracking (active, banned, flood wait)
- **Failover System**: Automatic retry and account switching on failures

## Bot Interface Architecture
- **Modular Handlers**: Separate handler classes for admin and user operations
- **Keyboard System**: Static keyboard generation with role-based UI elements
- **State-based Interactions**: FSM for complex multi-step user flows
- **Callback Query Routing**: Centralized callback handling with data-driven routing

## View Boosting System
- **Message View Increment**: Uses Telegram's GetMessagesViewsRequest API
- **Read Acknowledgment**: Marks messages as read for realistic interaction patterns
- **Retry Logic**: Configurable retry attempts with exponential backoff
- **Scheduled Operations**: Support for both instant and scheduled boosting

## Error Handling & Logging
- **Comprehensive Logging**: File and console logging with rotating handlers
- **Telegram Error Management**: Specific handling for FloodWaitError, banned accounts, and API limits
- **Operation Tracking**: Database logging of all operations (joins, boosts, errors)
- **Admin Notifications**: Real-time notifications for critical system events

## File Structure Organization
- **Modular Design**: Separation of concerns with dedicated modules for each functionality
- **Handler Pattern**: Separate handlers for admin and user operations
- **Utility Layer**: Common functions for validation and formatting
- **Configuration Isolation**: Environment-based configuration management

# External Dependencies

## Telegram APIs
- **Telegram Bot API**: Through Aiogram framework for bot interface
- **Telegram Client API**: Through Telethon for account operations and view boosting
- **API Credentials**: Requires API_ID, API_HASH from Telegram, and BOT_TOKEN from BotFather

## Python Packages
- **aiogram**: Main bot framework for Telegram bot operations
- **telethon**: Telegram client library for advanced operations
- **aiosqlite**: Async SQLite database operations
- **python-dotenv**: Environment variable management
- **asyncio**: Async/await support for concurrent operations

## System Requirements
- **Cross-Platform**: Designed for Windows and Linux compatibility
- **Python 3.7+**: Modern async/await syntax requirements
- **File System**: Local file storage for SQLite database and Telethon sessions
- **Network**: Internet connectivity for Telegram API access

## Environment Configuration
- **BOT_TOKEN**: Telegram bot token from BotFather
- **API_ID/API_HASH**: Telegram API credentials for client operations
- **ADMIN_IDS**: Comma-separated list of admin user IDs
- **Database Path**: Configurable SQLite database location
- **Session Directory**: Configurable location for Telethon session files