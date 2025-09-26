import time
import threading
from typing import Optional
from datetime import datetime, timedelta, timezone


class DailyLossTracker:
    """Tracks daily losses to implement circuit breaker functionality."""
    def __init__(self, max_daily_loss: float):
        self.max_daily_loss = max_daily_loss
        self.daily_pnl = 0.0
        self.reset_time = self._get_next_reset_time()
        self.lock = threading.Lock()
        self.start_balance = 0.0
    
    def _get_next_reset_time(self) -> float:
        """Get the timestamp for next daily reset (00:00 WIB)."""
        wib_tz = timezone(timedelta(hours=7))
        now = datetime.now(wib_tz)
        # Reset at 00:00 WIB (7:00 UTC the previous day)
        next_reset = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 7:00 UTC = 00:00 WIB next day
        if now.time() < datetime(1900, 1, 1, 7).time():  # If it's before 7:00 WIB today
            next_reset = next_reset - timedelta(days=1)  # Reset time was yesterday 7:00 UTC
        
        return next_reset.timestamp()
    
    def update_starting_balance(self, balance: float):
        """Update the starting balance for daily loss calculations."""
        self.start_balance = balance
    
    def update_pnl(self, pnl: float):
        """Update daily P&L."""
        with self.lock:
            # Check if we need to reset the daily counter
            if time.time() >= self.reset_time:
                self.reset_daily_counter()
            self.daily_pnl += pnl
    
    def get_daily_loss_percentage(self) -> float:
        """Get daily loss as a percentage of starting balance."""
        if self.start_balance <= 0:
            return 0.0
        with self.lock:
            if time.time() >= self.reset_time:
                self.reset_daily_counter()
            return abs(self.daily_pnl) / self.start_balance
    
    def is_circuit_breaker_active(self) -> bool:
        """Check if daily loss has exceeded the threshold."""
        with self.lock:
            if time.time() >= self.reset_time:
                self.reset_daily_counter()
            if self.start_balance <= 0:
                return False
            return abs(self.daily_pnl) / self.start_balance > self.max_daily_loss
    
    def reset_daily_counter(self):
        """Reset daily P&L counter."""
        self.daily_pnl = 0.0
        self.reset_time = self._get_next_reset_time()
    
    def get_daily_pnl(self) -> float:
        """Get current daily P&L."""
        with self.lock:
            if time.time() >= self.reset_time:
                self.reset_daily_counter()
            return self.daily_pnl