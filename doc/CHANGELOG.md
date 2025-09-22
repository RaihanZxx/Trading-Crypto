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

## [Unreleased]

### Planned
- Add unit tests for all modules
- Implement additional exchange connectors
- Add more sophisticated screener algorithms
- Create web dashboard for visualizing data
- Add email notification support
- Implement user configuration system