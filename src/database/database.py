import sqlite3
import os
from typing import Dict, Optional, Tuple


class Database:
    def __init__(self, db_path: str = "data/crypto_screener.db"):
        """Initialize database connection and create tables if they don't exist."""
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for storing open prices at 7:00 WIB (UTC+7) / 00:00 UTC
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS open_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    open_price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            ''')
            
            # Table for storing screener results
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS screener_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    top_gainers TEXT,
                    top_losers TEXT
                )
            ''')
            
            conn.commit()

    def save_open_price(self, symbol: str, open_price: float, timestamp: str):
        """Save open price for a symbol at specific timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO open_prices (symbol, open_price, timestamp)
                VALUES (?, ?, ?)
            ''', (symbol, open_price, timestamp))
            conn.commit()

    def get_open_price(self, symbol: str, date: str) -> Optional[float]:
        """Get open price for a symbol on specific date."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT open_price FROM open_prices 
                WHERE symbol = ? AND timestamp LIKE ?
            ''', (symbol, f"{date}%"))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_all_open_prices(self, date: str) -> Dict[str, float]:
        """Get all open prices for a specific date."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, open_price FROM open_prices 
                WHERE timestamp LIKE ?
            ''', (f"{date}%",))
            results = cursor.fetchall()
            return {symbol: price for symbol, price in results}

    def save_screener_result(self, timestamp: str, top_gainers: str, top_losers: str):
        """Save screener result."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO screener_results (timestamp, top_gainers, top_losers)
                VALUES (?, ?, ?)
            ''', (timestamp, top_gainers, top_losers))
            conn.commit()

    def get_latest_screener_result(self) -> Optional[Tuple[str, str, str]]:
        """Get the latest screener result."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, top_gainers, top_losers 
                FROM screener_results 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            return cursor.fetchone()