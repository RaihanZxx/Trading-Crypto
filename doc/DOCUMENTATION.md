# Crypto Trading Screener Documentation

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Risk Management System](#risk-management-system)
5. [Configuration](#configuration)
6. [Usage](#usage)
7. [Modules](#modules)
8. [OFI Engine](#ofi-engine)
9. [OFI Sentinel](#ofi-sentinel)
10. [Testing](#testing)
11. [Error Handling](#error-handling)
12. [Database Schema](#database-schema)
13. [API Documentation](#api-documentation)

## Overview

The Crypto Trading Screener is an automated tool that monitors cryptocurrency futures markets and identifies top gainers and losers based on price changes from the daily opening price. The system fetches data from the Bitget exchange, stores it in a local database, and sends notifications via Telegram.

In addition to the screener, the project includes an OFI (Order Flow Imbalance) engine implemented in Rust for high-performance analysis of market data from WebSocket connections. This allows for real-time trading signal detection based on order book and trade data.

Most importantly, the system now features the **OFI Sentinel**, a Rust-based daemon application that runs continuously and manages multiple concurrent analysis tasks. It orchestrates the entire trading operation by periodically calling Python services for screening and execution.

## Project Structure

```
Trading-Crypto/
├── config/
├── data/
│   ├── crypto_screener.db
│   └── telegram_state.json
├── doc/
│   ├── CODE_OF_CONDUCT.md
│   ├── CONTRIBUTING.md
│   ├──SECURITY.md
│   └── DOCUMENTATION.md
├── src/
│   ├── Cargo.toml
│   ├── main.rs                 # OFI Sentinel - main daemon application in Rust
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── exchange_service.py
│   │   └── websocket.rs
│   ├── database/
│   │   ├── __init__.py
│   │   └── database.py
│   ├── execution_service/
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── screener/
│   │   ├── __init__.py
│   │   └── screener.py
│   ├── strategy/
│   │   └── OFI/
│   │       ├── __init__.py
│   │       ├── data.rs
│   │       ├── engine.rs
│   │       ├── ofi.rs
│   │       ├── signals.rs
│   │       ├── wrapper.py
│   │       └── websocket.rs
│   ├── test/
│   │   └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── lib.rs
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
- Now functions as a service layer callable by the OFI Sentinel

### Execution Service
- `execution_service/manager.py`: Python service for trade execution and advanced risk management
- Contains `TradeManager` class for executing trades and managing positions
- Implements 1% risk management system with dynamic position sizing based on account equity
- Manages automatic stop-loss orders at 1% from entry price
- Provides real-time position monitoring and tracking
- Includes portfolio-level risk management with configurable maximum concurrent positions
- Features position closure functionality and risk metrics reporting

### Strategy
- `strategy/OFI/`: Implementation of Order Flow Imbalance analysis
  - `engine.rs`: Main analysis engine for processing market data
  - `data.rs`: Data structures for market data (order book, trades)
  - `ofi.rs`: Core OFI calculation algorithms
  - `signals.rs`: Algorithms for detecting trading signals based on market data
  - `websocket.rs`: WebSocket connection for real-time market data
  - `wrapper.py`: Python wrapper for the Rust OFI engine

### Utils
- `lib.rs`: Rust module definitions and PyO3 bindings
- `telegram.py`: Telegram notification system

### Test
- Currently empty but will contain unit tests in future versions

### Main Application
- `main.rs`: OFI Sentinel - Rust-based daemon application that manages concurrent analysis tasks
- Orchestrates the entire trading operation with periodic Python service calls

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

## OFI Sentinel

The OFI Sentinel is a Rust-based daemon application that runs continuously (24/7) and manages multiple concurrent analysis tasks. It serves as the brain of the entire trading operation, orchestrating communication between Rust and Python components.

### Features
- **Concurrent Analysis**: Manages multiple analysis tasks running simultaneously, each dedicated to a specific cryptocurrency symbol
- **Real-time Monitoring**: Each task maintains a persistent WebSocket connection to receive market data
- **Dynamic Watchlist**: Periodically calls Python Screener service to get an updated list of relevant symbols to monitor (e.g., every 15 minutes)
- **Signal Processing**: Collects trading signals from all analysis tasks via MPSC channels
- **Execution Delegation**: Calls Python Execution Service when valid trading signals are detected
- **Resource Management**: Dynamically starts and stops analysis tasks based on watchlist changes

### Architecture
1. **Main Sentinel Loop** (`main.rs`):
   - Manages the lifecycle of concurrent analysis tasks
   - Runs a periodic scheduler to refresh the watchlist
   - Aggregates signals from all analysis tasks
   - Delegates trade execution to Python service when signals are received

2. **Analysis Tasks** (async tasks in `main.rs`):
   - Each task is dedicated to a single cryptocurrency symbol
   - Maintains WebSocket connection via existing `connectors/websocket.rs`
   - Processes real-time market data using OFI engine
   - Sends detected signals to main loop via MPSC channel

3. **Python Integration** (via PyO3):
   - Calls `get_top_candidates()` function in `screener/screener.py` for watchlist updates
   - Calls `handle_trade_signal()` function in `execution_service/manager.py` for trade execution

### Configuration
The Sentinel uses the same configuration system as the OFI engine, loading parameters from `config.toml` and API credentials from environment variables.

### Parameters
- Watchlist refresh interval (default: 15 minutes)
- Maximum number of concurrent analysis tasks
- Signal confidence thresholds for execution
- Analysis duration per cycle (from config.toml)

## Risk Management System

The system includes a sophisticated risk management system that implements 1% risk per trade methodology to protect capital and ensure sustainable trading performance.

### Key Features

- **Dynamic Position Sizing**: Position size is calculated based on 1% of current account equity, ensuring risk is proportional to available capital
- **Stop-Loss Automation**: Each trade automatically includes a stop-loss order at 1% from entry price
- **Concurrent Position Limits**: Configurable maximum number of positions to prevent over-leveraging
- **Real-time Position Monitoring**: Each position is continuously monitored until closed
- **Risk Metrics Dashboard**: Provides summary of active positions and risk exposure

### Risk Calculation Formula

The position size is calculated using the formula:
```
Position Size = (Account Equity * Risk Percentage) / (Entry Price * Stop-Loss Percentage)
```

For example, with $10,000 equity and 1% risk per trade:
- Risk Amount = $10,000 * 0.01 = $100
- For BTC at $50,000 with 1% stop-loss: Position Size = $100 / ($50,000 * 0.01) = 0.2 contracts

### Configuration Parameters

The risk management system uses the following configuration parameters from `config.toml`:

```toml
[execution]
# Risk management parameters
max_concurrent_positions = 5           # Maximum positions open at once
stop_loss_percent = 0.01              # Stop loss as percentage (0.01 = 1%)
risk_percentage = 0.01                # Risk per trade as percentage of equity (0.01 = 1%)
use_dynamic_risk = true               # Enable dynamic risk based on account equity
```

### Position Management

The system provides comprehensive position management:

- **Position Tracking**: Each position is tracked with entry price, size, stop-loss level, and order IDs
- **Automatic Stop-Loss**: Stop-loss orders are placed immediately after trade execution
- **Real-time Monitoring**: Background threads monitor position status on exchange
- **Position Closure**: Automatic removal from tracking when position is closed
- **Risk Summary**: Provides total risk exposure across all positions

### API Functions

The execution service provides several key functions:

- `execute_trade(signal)`: Execute a trade with proper risk management
- `_calculate_position_size(price)`: Calculate position size based on risk parameters
- `get_active_positions()`: Get all currently tracked positions
- `get_position_summary()`: Get risk metrics summary
- `close_position(symbol)`: Manually close a specific position
- `_monitor_position(symbol)`: Internal monitoring function for position tracking

### Error Handling

The risk management system implements robust error handling:

- Validates account equity before calculating position size
- Handles API errors gracefully without stopping the system
- Provides fallback mechanisms for position tracking
- Implements retry mechanisms for exchange API calls
- Logs all risk management decisions for audit trails

## Configuration

The system uses a centralized configuration system with parameters stored in `config.toml` and API credentials stored in environment variables for security.

### config.toml Structure

```toml
# OFI Engine Configuration
[ofi]
websocket_url = "wss://ws.bitget.com/v2/ws/public"
default_imbalance_threshold = 3.0
default_absorption_threshold = 1000.0
default_delta_threshold = 50000.0
default_lookback_period_ms = 5000
analysis_duration_limit_ms = 3600000
analysis_duration_per_cycle_ms = 5000  # Duration for each analysis cycle
trade_storage_limit = 200
strong_signal_confidence = 0.9
reversal_signal_confidence = 0.8
exhaustion_signal_confidence = 0.7

# Strategy Configuration
[strategy]
imbalance_threshold = 3.0
absorption_threshold = 1000.0
delta_threshold = 50000.0
lookback_period_ms = 5000

# Screener Configuration
[screener]
top_n_gainers = 10
top_n_losers = 10
min_price_change_percent = 1.0

# Execution Configuration
[execution]
# Risk management parameters
max_concurrent_positions = 5
stop_loss_percent = 0.01
risk_percentage = 0.01  # 1% of wallet balance for dynamic risk
use_dynamic_risk = true  # Set to true to use dynamic risk calculation
```

### Configuration Parameters

#### [ofi] Section
- `websocket_url`: WebSocket endpoint for market data
- `default_imbalance_threshold`: Minimum ratio for detecting order book imbalances
- `default_absorption_threshold`: Threshold for absorption detection
- `default_delta_threshold`: Threshold for cumulative order flow significance
- `default_lookback_period_ms`: Time window (in ms) for analysis calculations
- `analysis_duration_limit_ms`: Maximum allowed analysis duration per symbol (in ms)
- `analysis_duration_per_cycle_ms`: Duration of each analysis cycle (in ms) - controls how long each task analyzes a symbol before checking for new signals
- `trade_storage_limit`: Maximum number of trades to keep in memory per symbol
- `strong_signal_confidence`: Confidence level for strong signals (0.0-1.0)
- `reversal_signal_confidence`: Confidence level for reversal signals (0.0-1.0)
- `exhaustion_signal_confidence`: Confidence level for exhaustion signals (0.0-1.0)

#### [execution] Section
- `max_concurrent_positions`: Maximum number of positions that can be open simultaneously
- `stop_loss_percent`: Stop loss as percentage of entry price (e.g., 0.01 for 1%)
- `risk_percentage`: Risk amount as percentage of total equity per trade (e.g., 0.01 for 1%)
- `use_dynamic_risk`: Whether to use dynamic risk calculation based on current equity
- `stop_loss_percent`: Stop loss as percentage of entry price

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