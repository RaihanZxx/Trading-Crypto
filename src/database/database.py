import sqlite3
import os
import threading
from typing import Dict, Optional, Tuple
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = "data/crypto_screener.db"):
        """Initialize database connection and create tables if they don't exist."""
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()
        self.init_db()
        self._create_indexes()

    def _get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False  # Allow connection usage across threads
            )
            # Optimize for frequent writes
            self._local.connection.execute("PRAGMA journal_mode=WAL;")  # Better for concurrent access
            self._local.connection.execute("PRAGMA synchronous=NORMAL;")  # Balance between speed and safety
            self._local.connection.execute("PRAGMA cache_size=10000;")  # Increase cache size
            self._local.connection.execute("PRAGMA temp_store=memory;")  # Store temp data in memory
        return self._local.connection

    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor with automatic commit/rollback."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp)
                )
            ''')
            
            # Table for storing trade execution logs for monitoring and analysis
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    position_size REAL NOT NULL,
                    pnl REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'open',
                    entry_timestamp TEXT NOT NULL,
                    exit_timestamp TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def _create_indexes(self):
        """Create indexes to optimize query performance."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Index for open_prices table
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_open_prices_symbol_timestamp ON open_prices (symbol, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_open_prices_timestamp ON open_prices (timestamp)')
            
            # Index for trade_logs table
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_logs_symbol_status ON trade_logs (symbol, status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_logs_timestamp ON trade_logs (created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_logs_status ON trade_logs (status)')
            
            conn.commit()

    def save_open_price(self, symbol: str, open_price: float, timestamp: str):
        """Save open price for a symbol at specific timestamp."""
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT OR REPLACE INTO open_prices (symbol, open_price, timestamp)
                VALUES (?, ?, ?)
            ''', (symbol, open_price, timestamp))

    def get_all_open_prices(self, date: str) -> Dict[str, float]:
        """Get all open prices for a specific date."""
        with self.get_cursor() as cursor:
            cursor.execute('''
                SELECT symbol, open_price FROM open_prices 
                WHERE timestamp LIKE ?
            ''', (f"{date}%",))
            results = cursor.fetchall()
            return {symbol: price for symbol, price in results}
    
    def save_trade_log(self, symbol: str, signal_type: str, entry_price: float, 
                      position_size: float, entry_timestamp: str, status: str = 'open'):
        """Save trade execution log."""
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO trade_logs (symbol, signal_type, entry_price, position_size, entry_timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (symbol, signal_type, entry_price, position_size, entry_timestamp, status))
    
    def update_trade_log(self, symbol: str, exit_price: float, pnl: float, 
                        exit_timestamp: str, trade_id: Optional[int] = None):
        """Update trade log with exit information."""
        with self.get_cursor() as cursor:
            if trade_id:
                cursor.execute('''
                    UPDATE trade_logs 
                    SET exit_price = ?, pnl = ?, exit_timestamp = ?, status = 'closed'
                    WHERE id = ?
                ''', (exit_price, pnl, exit_timestamp, trade_id))
            else:
                # Update the latest open trade for this symbol
                cursor.execute('''
                    UPDATE trade_logs 
                    SET exit_price = ?, pnl = ?, exit_timestamp = ?, status = 'closed'
                    WHERE symbol = ? AND status = 'open'
                    ORDER BY id DESC
                    LIMIT 1
                ''', (exit_price, pnl, exit_timestamp, symbol))
    
    def get_open_trades(self) -> list:
        """Get all currently open trades."""
        with self.get_cursor() as cursor:
            cursor.execute('''
                SELECT id, symbol, signal_type, entry_price, position_size, entry_timestamp
                FROM trade_logs 
                WHERE status = 'open'
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
    
    def get_trade_performance(self, symbol: Optional[str] = None) -> dict:
        """Get performance metrics for trades."""
        with self.get_cursor() as cursor:
            if symbol:
                cursor.execute('''
                    SELECT COUNT(*) as total_trades, 
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                           AVG(pnl) as avg_pnl,
                           SUM(pnl) as total_pnl
                    FROM trade_logs
                    WHERE symbol = ? AND status = 'closed'
                ''', (symbol,))
            else:
                cursor.execute('''
                    SELECT COUNT(*) as total_trades, 
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                           AVG(pnl) as avg_pnl,
                           SUM(pnl) as total_pnl
                    FROM trade_logs
                    WHERE status = 'closed'
                ''')
            result = cursor.fetchone()
            
            if result is not None and result[0] > 0:
                total_trades, winning_trades, avg_pnl, total_pnl = result
                win_rate = winning_trades / total_trades if total_trades > 0 else 0
                return {
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'win_rate': win_rate,
                    'avg_pnl': avg_pnl or 0.0,
                    'total_pnl': total_pnl or 0.0
                }
            else:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'win_rate': 0.0,
                    'avg_pnl': 0.0,
                    'total_pnl': 0.0
                }