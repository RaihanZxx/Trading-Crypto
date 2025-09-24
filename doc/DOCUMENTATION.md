# Crypto Trading Screener Documentation

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Modules](#modules)
7. [OFI Engine](#ofi-engine)
8. [Testing](#testing)
9. [Error Handling](#error-handling)
10. [Database Schema](#database-schema)
11. [API Documentation](#api-documentation)
12. [Changelog](#changelog)

## Overview

The Crypto Trading Screener is an automated tool that monitors cryptocurrency futures markets and identifies top gainers and losers based on price changes from the daily opening price. The system fetches data from the Bitget exchange, stores it in a local database, and sends notifications via Telegram.

In addition to the screener, the project includes an OFI (Order Flow Imbalance) engine implemented in Rust for high-performance analysis of market data from WebSocket connections. This allows for real-time trading signal detection based on order book and trade data.

## Project Structure

```
Trading-Crypto/
├── config/
├── data/
│   ├── crypto_screener.db
│   └── telegram_state.json
├── doc/
│   ├── CHANGELOG.md
│   ├── CODE_OF_CONDUCT.md
│   ├── CONTRIBUTING.md
│   └── DOCUMENTATION.md
├── src/
│   ├── Cargo.toml
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── exchange_service.py
│   │   └── websocket.rs
│   ├── database/
│   │   ├── __init__.py
│   │   └── database.py
│   ├── screener/
│   │   ├── __init__.py
│   │   └── screener.py
│   ├── strategy/
│   │   └── OFI/
│   │       ├── __init__.py
│   │       ├── data.rs
│   │       ├── engine.rs
│   │       ├── signals.rs
│   │       ├── wrapper.py
│   │       └── websocket.rs
│   ├── test/
│   │   └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── telegram.py
│   └── main.py
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

2. Ensure Rust is installed:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   ```

3. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -e .
   ```

5. Build the Rust components:
   ```bash
   cd src && cargo build --release
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

Use the OFI engine for real-time analysis:
```bash
# Using the Python wrapper to call the Rust engine
python -c "from src.strategy.OFI.wrapper import analyze_symbol; signal = analyze_symbol('BTCUSDT'); print(signal)"
```

## Modules

### Connectors
- `exchange_service.py`: Handles communication with the Bitget API
- `websocket.rs`: Rust implementation for WebSocket connections to real-time market data

### Database
- `database.py`: Manages SQLite database for storing open prices and screener results
- Ensures data persistence between runs

### Screener
- `screener.py`: Core logic for fetching prices, calculating changes, and identifying gainers/losers

### Strategy
- `strategy/OFI/`: Implementation of Order Flow Imbalance analysis
  - `engine.rs`: Main analysis engine for processing market data
  - `data.rs`: Data structures for market data (order book, trades)
  - `signals.rs`: Algorithms for detecting trading signals based on market data
  - `wrapper.py`: Python wrapper for the Rust OFI engine

### Utils
- `telegram.py`: Telegram notification system

### Test
- Currently empty but will contain unit tests in future versions

## OFI Engine

The OFI (Order Flow Imbalance) engine is a high-performance analysis engine written in Rust. It connects to exchange WebSocket endpoints to receive real-time order book and trade data, then applies sophisticated algorithms to detect trading opportunities.

### Features
- Real-time order book updates
- Trade flow analysis
- Order Flow Imbalance calculation
- Signal detection based on multiple criteria
- Low-latency processing using Rust

### How it Works
1. Connects to exchange WebSocket API using Rust
2. Receives order book snapshots and trade updates
3. Calculates OFI metrics based on order book dynamics
4. Detects signals when certain thresholds are met
5. Returns signals via Python wrapper using PyO3

### Parameters
- `imbalance_ratio`: Threshold for order flow imbalance (default: 3.0)
- `analysis_duration_ms`: Duration to run analysis (default: 5000ms)
- `delta_threshold`: Threshold for cumulative order flow (default: 50000.0)
- `lookback_period_ms`: Time window for analysis (default: 5000ms)

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
- OFI engine functionality tests

## Error Handling

The system implements robust error handling for:
- Network connection issues (ConnectionResetError, Timeout)
- API errors
- Database errors
- WebSocket connection failures
- Retry mechanisms with exponential backoff for transient failures

Error handling strategies:
1. **Network Errors**: Implements exponential backoff retry mechanism (up to 3 attempts)
2. **API Errors**: Logs error details and continues processing other symbols
3. **Database Errors**: Attempts to reconnect and retry operations
4. **WebSocket Errors**: Handles connection drops and reconnection attempts
5. **General Exceptions**: Comprehensive logging for debugging

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

### OFI Engine (Rust)
- `run_analysis(symbol, imbalance_ratio, duration_ms, delta_threshold, lookback_period_ms)`: Performs real-time OFI analysis for a symbol
- `update_order_book(book)`: Updates order book data
- `add_trade(trade)`: Adds trade data
- `analyze_symbol(symbol)`: Analyzes a symbol for trading signals

### OFI Wrapper (Python)
- `analyze_symbol(symbol, imbalance_ratio, analysis_duration_ms)`: Analyze a symbol for trading signals
- `get_order_book(symbol)`: Get current order book for a symbol

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.