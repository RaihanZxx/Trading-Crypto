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