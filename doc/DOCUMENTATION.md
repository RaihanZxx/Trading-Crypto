# Crypto Trading Screener Documentation

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Modules](#modules)
7. [Testing](#testing)
8. [Error Handling](#error-handling)
9. [Database Schema](#database-schema)
10. [API Documentation](#api-documentation)
11. [Changelog](#changelog)

## Overview

The Crypto Trading Screener is an automated tool that monitors cryptocurrency futures markets and identifies top gainers and losers based on price changes from the daily opening price. The system fetches data from the Bitget exchange, stores it in a local database, and sends notifications via Telegram.

## Project Structure

```
Trading-Crypto/
├── src/
│   ├── connectors/
│   │   ├── __init__.py
│   │   └── exchange_service.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── database.py
│   ├── screener/
│   │   ├── __init__.py
│   │   └── screener.py
│   ├── test/
│   │   └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── telegram.py
│   └── main.py
├── data/
│   ├── crypto_screener.db
│   └── telegram_state.json
├── doc/
│   ├── CHANGELOG.md
│   ├── CODE_OF_CONDUCT.md
│   ├── CONTRIBUTING.md
│   └── DOCUMENTATION.md
├── .env
├── .env.example
├── .gitignore
├── LICENSE
├── pyproject.toml
└── README.md
```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/RaihanZxx/Trading-Crypto
   cd Trading-Crypto
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   ```

## Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit the `.env` file to add:
- Bitget API credentials (API key, secret key, passphrase)
- Telegram bot token and chat ID

## Usage

Run the screener:
```bash
python src/main.py
```

The screener will automatically:
1. Fetch open prices for all futures symbols at 7:00 AM WIB (00:00 UTC)
2. Calculate price changes throughout the day
3. Identify top 10 gainers and losers
4. Send results via Telegram

## Modules

### Connectors
- `exchange_service.py`: Handles communication with the Bitget API
- Implements retry mechanisms with exponential backoff for network resilience

### Database
- `database.py`: Manages SQLite database for storing open prices and screener results
- Ensures data persistence between runs

### Screener
- `screener.py`: Core logic for fetching prices, calculating changes, and identifying gainers/losers

### Utils
- `telegram.py`: Telegram notification system

### Test
- Currently empty but will contain unit tests in future versions

## Testing

Currently, the project does not have comprehensive unit tests. This is planned for future releases.

To run any existing tests:
```bash
# No tests currently implemented
```

Planned testing improvements:
- Unit tests for all modules
- Integration tests for exchange API connectivity
- Database operation tests
- Notification system tests

## Error Handling

The system implements robust error handling for:
- Network connection issues (ConnectionResetError, Timeout)
- API errors
- Database errors
- Retry mechanisms with exponential backoff for transient failures

Error handling strategies:
1. **Network Errors**: Implements exponential backoff retry mechanism (up to 3 attempts)
2. **API Errors**: Logs error details and continues processing other symbols
3. **Database Errors**: Attempts to reconnect and retry operations
4. **General Exceptions**: Comprehensive logging for debugging

## Database Schema

The project uses SQLite for data persistence with the following schema:

### open_prices table
```sql
CREATE TABLE open_prices (
    symbol TEXT PRIMARY KEY,
    open_price REAL,
    timestamp DATETIME
);
```

### screener_results table
```sql
CREATE TABLE screener_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    open_price REAL,
    current_price REAL,
    change_percent REAL,
    result_type TEXT,  -- 'gainer' or 'loser'
    timestamp DATETIME
);
```

## API Documentation

### exchange_service.py
- `get_all_futures_symbols()`: Fetches all available futures symbols from Bitget
- `get_open_price(symbol)`: Gets the opening price for a specific symbol
- `get_current_price(symbol)`: Gets the current price for a specific symbol

### database.py
- `init_db()`: Initializes the database with required tables
- `save_open_price(symbol, open_price)`: Saves opening price for a symbol
- `get_open_price(symbol)`: Retrieves opening price for a symbol
- `save_screener_result(symbol, open_price, current_price, change_percent, result_type)`: Saves screener results
- `get_latest_gainers(limit)`: Retrieves latest top gainers
- `get_latest_losers(limit)`: Retrieves latest top losers

### screener.py
- `fetch_open_prices()`: Fetches and stores opening prices for all symbols
- `calculate_changes()`: Calculates price changes and identifies gainers/losers
- `run_screener()`: Main screener execution function

### telegram.py
- `send_telegram_message(message)`: Sends a message via Telegram bot

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.