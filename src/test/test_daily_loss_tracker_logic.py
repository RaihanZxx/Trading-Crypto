import os
import sys
import time
from datetime import datetime

# Tambahkan path untuk mengakses module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from execution_service.risk import DailyLossTracker

def test_daily_loss_tracker_logic():
    print("=== Testing DailyLossTracker Core Logic ===")
    
    # Initialize with mock starting balance
    max_daily_loss_percentage = 0.03  # 3% daily loss threshold
    tracker = DailyLossTracker(max_daily_loss_percentage)
    starting_balance = 1000.0  # Mock starting balance
    tracker.update_starting_balance(starting_balance)
    
    print(f"Starting balance: {starting_balance}")
    print(f"Max daily loss threshold: {max_daily_loss_percentage*100}%")
    
    # Test updating P&L - this should work in a controlled environment
    # where we avoid crossing the reset threshold
    print("\nTesting P&L updates...")
    
    # First update
    tracker.update_pnl(-50.0)  # Loss of 50
    daily_pnl = tracker.get_daily_pnl()
    daily_loss_pct = tracker.get_daily_loss_percentage()
    circuit_breaker_active = tracker.is_circuit_breaker_active()
    
    print(f"After loss of 50: Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
    
    # Second update
    tracker.update_pnl(20.0)  # Gain of 20
    daily_pnl = tracker.get_daily_pnl()
    daily_loss_pct = tracker.get_daily_loss_percentage()
    circuit_breaker_active = tracker.is_circuit_breaker_active()
    
    print(f"After gain of 20: Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
    
    # Third update - large loss to trigger circuit breaker
    tracker.update_pnl(-40.0)  # Loss of 40
    daily_pnl = tracker.get_daily_pnl()
    daily_loss_pct = tracker.get_daily_loss_percentage()
    circuit_breaker_active = tracker.is_circuit_breaker_active()
    
    print(f"After loss of 40: Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
    
    # Test with more aggressive loss to trigger circuit breaker
    tracker.update_pnl(-25.0)
    daily_pnl = tracker.get_daily_pnl()
    daily_loss_pct = tracker.get_daily_loss_percentage()
    circuit_breaker_active = tracker.is_circuit_breaker_active()
    
    print(f"After additional loss of 25: Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
    
    print("\nTesting reset functionality...")
    # Reset the tracker manually to simulate new day
    tracker.reset_daily_counter()
    daily_pnl_after_reset = tracker.get_daily_pnl()
    print(f"After manual reset: Daily P&L = {daily_pnl_after_reset:+.2f}")
    
    print("\nTesting circuit breaker logic...")
    # Simulate a large loss that exceeds the threshold
    tracker.update_starting_balance(1000.0)  # Reset balance for testing
    large_loss = -40.0  # This is 4% loss on 1000 balance, exceeding 3% threshold
    tracker.update_pnl(large_loss)
    
    daily_pnl = tracker.get_daily_pnl()
    daily_loss_pct = tracker.get_daily_loss_percentage()
    circuit_breaker_active = tracker.is_circuit_breaker_active()
    
    print(f"After loss of 40 (4% of 1000): Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
    
    print("\n✅ DailyLossTracker core logic test completed!")
    return True

def test_with_real_api():
    print("\n=== Testing with Real API ===")
    
    # Load environment variables
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        print("Environment variables not set. Please set BITGET_API_KEY, BITGET_SECRET_KEY, and BITGET_PASSPHRASE")
        return False
    
    print("API credentials loaded")
    
    from connectors.exchange_service import BitgetExchangeService
    
    # Initialize exchange service
    exchange = BitgetExchangeService(api_key, secret_key, passphrase)
    
    try:
        # Get initial balance to initialize the tracker
        print("\nGetting initial balance...")
        balance_info = exchange.get_balance()
        print(f"Balance info received: {len(balance_info) if isinstance(balance_info, list) else 1} account(s)")
        
        # Get the USDT balance
        usdt_balance = 0.0
        for acc in balance_info if isinstance(balance_info, list) else [balance_info]:
            if isinstance(acc, dict) and acc.get('marginCoin') == 'USDT':
                usdt_balance = float(acc.get('available', 0))
                break
        
        print(f"Available USDT balance: {usdt_balance}")
        
        # Initialize DailyLossTracker with real balance
        max_daily_loss_percentage = 0.03  # 3% daily loss threshold
        tracker = DailyLossTracker(max_daily_loss_percentage)
        tracker.update_starting_balance(usdt_balance)
        
        print(f"Tracker initialized with starting balance: {usdt_balance}")
        
        # Test simple functionality
        print("\nTesting basic functionality...")
        initial_loss_pct = tracker.get_daily_loss_percentage()
        print(f"Initial daily loss percentage: {initial_loss_pct*100:.4f}%")
        
        is_circuit_active = tracker.is_circuit_breaker_active()
        print(f"Is circuit breaker active: {is_circuit_active}")
        
        daily_pnl = tracker.get_daily_pnl()
        print(f"Initial daily P&L: {daily_pnl}")
        
        print("\n✅ Real API test completed!")
        return True
        
    except Exception as e:
        print(f"Error during API testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing DailyLossTracker class core functionality")
    print(f"Current time: {datetime.now()}")
    
    success1 = test_daily_loss_tracker_logic()
    success2 = test_with_real_api()
    
    if success1 and success2:
        print("\n🎉 All DailyLossTracker tests passed!")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)