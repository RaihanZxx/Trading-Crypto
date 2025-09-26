"""Execution service package for the OFI Sentinel system."""
from .manager import TradeManager, handle_trade_signal

__all__ = [
    "TradeManager",
    "handle_trade_signal"
]