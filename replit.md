# Overview

This is a Telegram View Booster Bot built with Python using Aiogram and Telethon. The bot allows users to manage Telegram channels and boost message views through automated account operations. It features a dual-interface system with separate admin and user panels, account management capabilities, and comprehensive logging.

The bot uses Aiogram for the main bot interface and Telethon for Telegram client operations like joining channels and boosting views. **Recent Update**: Now shows unique channels (consolidated view) and automatically uses all available accounts in rotation for view boosting.

# Recent Changes

## August 26, 2025
- **Group Call Rate Limiting Fix**: Fixed "Invalid group call" errors when multiple accounts try to join live streams simultaneously by adding 2-5 second delays between join attempts and improved error handling to continue with other accounts instead of stopping
- **Live Account Selection Feature**: Added user-configurable account count for live stream joining instead of automatically using all accounts
- **Account Configuration Menu**: New "Account Count" button in live management allows users to select how many accounts to use (1, 2, 3, 5, 10, 20, 50, all, or custom amount)
- **User Preference Storage**: Live account count setting is stored in user settings database and persists across sessions
- **Smart Live Monitoring**: Live monitor service now respects user's account preference when joining live streams
- **Enhanced Live Management UI**: Live management menu now displays current account usage setting and improved feature descriptions
- **2FA Authentication Support**: Completely redesigned 2FA handling to support two-factor authentication instead of asking users to disable it
- **Private Invite Link Fix**: Added support for new Telegram private invite link format (https://t.me/+xxxxx) alongside existing formats
- **Connection Management Improvements**: Fixed "Cannot send requests while disconnected" errors by improving Telethon client connection handling
- **Callback Query Timeout Fix**: Implemented safe callback query handling to prevent timeout crashes from expired button interactions
- **Enhanced Account Verification**: Added proper 2FA password state management and seamless verification flow
- **Auto Mode Output Fix**: Resolved missing completion messages after auto reactions/boost operations complete
- **Comprehensive State Management Fix**: Resolved all state clearing and callback routing issues causing empty state errors
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