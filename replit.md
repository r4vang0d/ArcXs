# Overview

This project is a Telegram View Booster Bot, designed to automate Telegram channel management and boost message views. It leverages a dual-interface system for both administrators and general users, offering features such as account management, comprehensive logging, and automated view boosting. The bot's core purpose is to provide an efficient solution for enhancing content visibility on Telegram channels, with a vision to become a versatile tool for content creators and marketers to increase engagement and reach.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework Architecture
- **Bot Framework**: Aiogram for the primary bot interface and user interactions.
- **Telegram Client**: Telethon for direct Telegram client operations (e.g., joining channels, boosting views).
- **State Management**: FSM (Finite State Machine) using Aiogram's built-in storage.
- **Configuration**: Environment variable-based configuration.

## Database Design
- **Engine**: SQLite with `aiosqlite` for asynchronous operations.
- **Connection Management**: Connection pooling with async locks for thread safety.
- **Schema**: Relational design including tables for users, accounts, channels, and logs.
- **Data Models**: Enum-based status tracking for accounts (e.g., ACTIVE, BANNED).

## Authentication & Authorization
- **Admin Access**: Verified via environment variable-defined admin IDs.
- **User Tiers**: Support for Free and Premium user classifications with feature restrictions.
- **Session Management**: Telethon session files stored persistently.

## Account Management Architecture
- **Multi-Account Support**: Manages multiple Telegram accounts via Telethon clients.
- **Session Storage**: File-based persistence for Telegram account sessions.
- **Health Monitoring**: Real-time tracking of account status (active, banned, flood wait).
- **Failover System**: Automatic retry mechanisms and account switching upon failures.

## Bot Interface Architecture
- **Modular Handlers**: Dedicated handlers for admin and user functionalities.
- **Keyboard System**: Static keyboard generation with role-based UI elements.
- **State-based Interactions**: FSM for managing complex, multi-step user workflows.
- **Callback Query Routing**: Centralized handling and data-driven routing for callbacks.

## View Boosting System
- **Message View Increment**: Utilizes Telegram's `GetMessagesViewsRequest` API.
- **Read Acknowledgment**: Marks messages as read for realistic user interaction patterns.
- **Retry Logic**: Configurable retry attempts with exponential backoff.
- **Scheduled Operations**: Supports both instant and scheduled boosting.

## Error Handling & Logging
- **Comprehensive Logging**: File and console logging with rotating handlers.
- **Telegram Error Management**: Specific handling for common Telegram API errors (e.g., FloodWaitError).
- **Operation Tracking**: Database logging of all bot operations.
- **Admin Notifications**: Real-time alerts for critical system events.

## File Structure Organization
- **Modular Design**: Separation of concerns with dedicated modules for distinct functionalities.
- **Handler Pattern**: Separate handler implementations for admin and user operations.
- **Utility Layer**: Common functions for validation and formatting tasks.

# External Dependencies

## Telegram APIs
- **Telegram Bot API**: Integrated via `Aiogram` for bot interaction.
- **Telegram Client API**: Integrated via `Telethon` for direct account operations and view boosting.
- **API Credentials**: Requires `API_ID`, `API_HASH` from Telegram, and `BOT_TOKEN` from BotFather.

## Python Packages
- **aiogram**: Core framework for Telegram bot development.
- **telethon**: Library for Telegram client operations.
- **aiosqlite**: Asynchronous SQLite database driver.
- **python-dotenv**: For managing environment variables.
- **asyncio**: Python's built-in library for asynchronous I/O.

## System Requirements
- **Python 3.7+**: Required for modern async/await syntax.
- **File System**: Local storage for SQLite database and Telethon sessions.
- **Network**: Internet connectivity for Telegram API access.

## Environment Configuration
- **BOT_TOKEN**: Telegram bot token.
- **API_ID/API_HASH**: Telegram API credentials.
- **ADMIN_IDS**: Comma-separated list of admin user IDs.
- **Database Path**: Configurable path for the SQLite database.
- **Session Directory**: Configurable path for Telethon session files.