# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-09-22

### Added
- Initial release of the Crypto Trading Screener
- Automated fetching of open prices at 7:00 AM WIB
- Price change calculation and ranking system
- Telegram notifications for top gainers and losers
- SQLite database for data persistence
- Exchange connector for Bitget API with retry mechanisms
- Error handling for network issues (ConnectionResetError, Timeout)
- Modular project structure with separate components for connectors, database, screener, and utilities

### Changed
- Improved project documentation with detailed installation and usage instructions
- Enhanced error handling with exponential backoff for API calls

### Fixed
- None (initial release)

### Security
- Environment variables for API keys and Telegram credentials
- No sensitive information stored in codebase

## [0.1.1] - 2025-09-23

### Fixed
- Screener now correctly uses today's open prices when run after 7:00 AM WIB instead of always using yesterday's open prices
- Resolved import order issues that were causing linting errors
- Fixed f-string formatting issues in Telegram notifications

### Planned
- Add unit tests for all modules
- Implement additional exchange connectors
- Add more sophisticated screener algorithms
- Create web dashboard for visualizing data
- Add email notification support
- Implement user configuration system

## [0.1.2] - 2025-09-24

### Added
- OFI (Order Flow Imbalance) engine implemented in Rust for high-performance analysis
- WebSocket connector for real-time market data using Rust
- OFI analysis module to detect trading signals based on order book and trade data
- Python wrapper for Rust OFI engine using PyO3
- New strategy directory for implementing trading strategies
- Data structures for order book and trade data handling in Rust
- Signal detection algorithms based on order flow analysis

### Changed
- Updated project structure to support multi-language development (Python + Rust)
- Enhanced README with information about Rust components and OFI engine
- Updated installation instructions to include Rust requirements
- Refactored architecture diagram to show new components

### Fixed
- Corrected import order issues identified in previous release
- Improved error handling in WebSocket connections

### Security
- Maintained environment variable approach for API credentials
- Added support for secure credential handling in multi-language environment

## [0.1.3] - 2025-09-24

### Added
- Configuration module (`config/mod.rs`) for centralized management of API keys and parameters
- Comprehensive input validation and sanitization for all public functions
- Enhanced error handling with proper `Result` types instead of `unwrap_or` patterns
- Configuration validation to ensure API keys and parameters are properly set
- Logging initialization method with configurable levels in Python bindings
- Centralized OFIEngine with configuration integration
- Support for loading OFI parameters from `config.toml` instead of hardcoded values
- Confidence level configuration parameters for trading signals
- Configuration validation to ensure required parameters are properly set

### Changed
- Unified OFIEngine definitions from multiple files into a single, configuration-driven implementation
- Migrated from hardcoded API keys to proper configuration management system
- Replaced all unsafe `unwrap_or` calls with proper error handling using `Result` types
- Made configuration parameters configurable via environment variables with validation
- Updated WebSocket parsing to properly validate and handle numeric conversions
- Enhanced Python bindings to use centralized configuration and proper error handling
- Updated data storage to use configurable limits instead of hardcoded values
- Separated credential loading (environment variables) from parameter loading (config.toml)
- Removed hardcoded default values, requiring explicit configuration in config.toml
- Enhanced error handling to return errors instead of using fallback defaults

### Fixed
- Security issue where API keys were stored but not properly validated or used
- Multiple memory safety issues in WebSocket message parsing
- Improper error propagation in trade and order book data processing
- Hardcoded configuration parameters that now use flexible, validated settings
- Removed duplicate OFIEngine definitions and unified into single implementation
- Fixed hardcoded confidence values in trading signal generation

### Security
- Added proper API key validation and verification
- Implemented secure configuration loading from environment variables
- Added input sanitization to prevent injection attacks
- Added validation for all user-provided parameters
- Separated credential handling (environment variables) from parameter handling (config.toml)

## [0.1.4] - 2025-09-25

### Added
- **OFI Sentinel**: Complete Rust-based daemon application (`src/main.rs`) that runs continuously as the core of the trading operation
- **Concurrent Analysis Tasks**: Implementation of multiple concurrent analysis tasks using `tokio::spawn` to monitor different cryptocurrency symbols simultaneously
- **OFI Sentinel Architecture**: Implementation of the complete OFI Sentinel system with task management, watchlist refresh scheduler, signal aggregation, and execution delegation
- **Python Service Layer**: Refactored Python screener to function as a service with `get_top_candidates()` function callable from Rust via PyO3
- **Execution Service**: Created Python execution service (`src/execution_service/manager.py`) with risk management and position sizing
- **Multi-language Communication**: Complete PyO3 integration for calling Python functions from Rust for both screening and execution
- **Dynamic Watchlist Management**: Implementation of 15-minute refresh cycle for watchlist with automatic start/stop of analysis tasks
- **Signal Aggregation**: MPSC channel implementation for collecting signals from all concurrent analysis tasks
- **Resource Management**: Dynamic task lifecycle management based on watchlist changes
- **Configuration from TOML**: Execution service now loads configuration parameters from config.toml instead of hardcoded values
- **Complete 1% Risk Management System**: Full implementation of 1% risk per trade functionality with dynamic position sizing based on account equity
- **Automatic Stop-Loss Orders**: Implementation of automatic stop-loss placement at 1% from entry price for all trades
- **Position Size Calculation**: Advanced position sizing algorithm that calculates position size based on 1% of current wallet balance divided by stop-loss distance
- **Position Monitoring System**: Real-time position monitoring with background threads that track position status and automatically clean up when positions are closed
- **Order Management**: Complete integration with Bitget API for placing market orders and stop-loss orders (including `place_order`, `place_stop_market_order`, `get_positions`, `get_open_orders`, `cancel_order`)
- **Risk Metrics Dashboard**: Functions to track and report risk metrics including total positions, total at-risk amount, and risk percentage of balance
- **Enhanced Trade Execution**: Full trade execution flow with proper error handling, position tracking, and monitoring
- **Position Closure Functionality**: Manual position closure functionality that handles both exchange positions and local tracking
- **Improved Error Handling**: Enhanced error handling in position monitoring to prevent hanging threads and resource leaks
- **Thread Safety**: Thread-safe implementation for position tracking and monitoring with proper locking mechanisms
- **API Integration**: Complete integration with Bitget's trade and position APIs for real-time monitoring

### Changed
- Converted the main application to OFI Sentinel daemon architecture instead of periodic screener
- Refactored Python screener module to serve as a service layer rather than the main application
- Updated architecture to follow inversion of control principle with Rust controlling the workflow
- Enhanced WebSocket implementation using existing `connectors/websocket.rs` for real-time data processing
- Integrated existing OFI engine components into the new sentinel architecture
- Updated project documentation to reflect the new OFI Sentinel system
- Modified application entry point to run as a continuous daemon service
- Moved hardcoded configuration values to configuration file (config.toml) for execution service
- Updated config.toml to include execution-specific parameters under [execution] section
- **Enhanced Execution Service**: Significantly improved the execution service (`src/execution_service/manager.py`) with complete risk management functionality
- **API Client**: Expanded the exchange service client (`src/connectors/exchange_service.py`) with comprehensive order and position management methods
- **Position Tracking**: Improved position tracking to include entry price, stop-loss price, order IDs, and timestamp information
- **Monitoring Logic**: Enhanced position monitoring to properly check exchange status before removing local tracking entries
- **Risk Calculation**: Updated position size calculation to properly implement 1% risk methodology using current equity
- **Configuration Loading**: Enhanced configuration validation and loading in execution service for risk parameters
- **Thread Management**: Improved thread lifecycle management for position monitoring with proper cleanup mechanisms

### Fixed
- Performance issues with single-threaded analysis by implementing concurrent task architecture
- Scalability limitations by enabling monitoring of multiple symbols simultaneously
- Communication inefficiencies between Python and Rust components
- Resource management issues by implementing proper task lifecycle management
- Security and maintainability by removing hardcoded values and centralizing configuration
- **Position Calculation Formula**: Corrected the position size calculation to properly implement 1% risk methodology (risk_amount / (price * stop_loss_percent))
- **Thread Resource Leak**: Fixed potential resource leaks in position monitoring by implementing proper stop mechanisms
- **Position State Management**: Resolved issues with position tracking state synchronization between local tracking and exchange status
- **Division by Zero**: Added protection against division by zero in risk calculation functions
- **Exchange Position Handling**: Improved handling of exchange position data format to prevent parsing errors
- **Error Propagation**: Enhanced error handling to provide better feedback during trade execution failures

### Security
- Maintained secure credential handling in the new architecture
- Enhanced security for multi-language communication via PyO3
- Added proper validation for inter-language function calls
- Maintained secure credential handling for API integration
- Added proper validation for all order parameters before submission to exchange
- Enhanced input validation for position management functions