#!/usr/bin/env python3
"""
Debug script to verify the position management logic.
This will test if the system properly blocks additional positions.
"""

import sys
import os
import threading
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from execution_service.manager import TradeManager

def test_position_blocking():
    print("Testing position blocking logic...")
    
    # Create a TradeManager instance
    tm = TradeManager()
    
    print(f"Initial active positions: {tm.get_active_positions()}")
    
    # Manually add a position to simulate existing position
    with tm.lock:
        tm.active_positions = {
            "BTCUSDT": {
                "entry_price": 60000.0,
                "size": 0.001,
                "side": "buy",  # This is a long position
                "stop_loss_price": 59500.0,
                "take_profit_price": 60500.0,
                "main_order_id": "test_order_123",
                "position_id": "test_pos_123",
                "timestamp": "2023-01-01T00:00:00Z"
            }
        }
    
    print(f"Active positions after manually adding: {tm.get_active_positions()}")
    
    # Test: Try to execute multiple signals when position exists
    print("\n--- Testing if signals are blocked when position exists ---")
    
    # Signal 1: Same direction (should be blocked)
    signal1 = {
        "symbol": "BTCUSDT",
        "signal_type": "StrongBuy",  # Same as current position
        "price": 60100.0,
        "timestamp": "2023-01-01T01:00:00Z"
    }
    
    result1 = tm.execute_trade(signal1)
    print(f"Result for same-direction signal: {result1}")
    
    # Signal 2: Opposite direction (should also be blocked now)
    signal2 = {
        "symbol": "BTCUSDT", 
        "signal_type": "StrongSell",  # Opposite to current position
        "price": 59900.0,
        "timestamp": "2023-01-01T02:00:00Z"
    }
    
    result2 = tm.execute_trade(signal2)
    print(f"Result for opposite-direction signal: {result2}")
    
    print(f"Active positions after blocked signals: {tm.get_active_positions()}")
    
    # Now, remove the position manually to simulate it being closed
    print("\n--- Simulating position closure ---")
    with tm.lock:
        if "BTCUSDT" in tm.active_positions:
            del tm.active_positions["BTCUSDT"]
            print("Removed BTCUSDT position manually to simulate closure")
    
    print(f"Active positions after manual removal: {tm.get_active_positions()}")
    
    # Test: Try to execute signal after position is closed (should succeed now)
    print("\n--- Testing if signal is allowed after position closure ---")
    
    signal3 = {
        "symbol": "BTCUSDT",
        "signal_type": "StrongBuy",  # New position
        "price": 59800.0,
        "timestamp": "2023-01-01T03:00:00Z"
    }
    
    # Mock exchange.place_order to avoid real trading
    original_place = tm.exchange.place_order
    def mock_place_order(symbol, side, size, order_type, preset_stop_loss_price=None, preset_stop_surplus_price=None, trade_side=None):
        return {
            'orderId': 'mock_order_456',
            'symbol': symbol,
            'side': side,
            'size': size,
            'price': 59800.0,
            'orderType': order_type,
            'status': 'filled'
        }
    tm.exchange.place_order = mock_place_order
    
    result3 = tm.execute_trade(signal3)
    print(f"Result for signal after closure: {result3}")
    
    print(f"Active positions after new signal: {tm.get_active_positions()}")
    
    # Restore original method
    tm.exchange.place_order = original_place
    
    print("\nPosition blocking test completed!")
    
    return result1, result2, result3

if __name__ == "__main__":
    test_position_blocking()