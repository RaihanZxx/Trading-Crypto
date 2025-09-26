import os
import sys
import time
from datetime import datetime

# Tambahkan path untuk mengakses module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from execution_service.risk import DailyLossTracker
from connectors.exchange_service import BitgetExchangeService

def test_daily_loss_tracker():
    print("=== Testing DailyLossTracker ===")
    
    # Load environment variables
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        print("Environment variables not set. Please set BITGET_API_KEY, BITGET_SECRET_KEY, and BITGET_PASSPHRASE")
        return False
    
    print("API credentials loaded")
    api_key_display = f"{api_key[:5]}...{api_key[-3:]}" if api_key else ""
    print(f"API Key: {api_key_display}")
    
    # Initialize exchange service
    exchange = BitgetExchangeService(api_key, secret_key, passphrase)
    
    # Get initial balance to initialize the tracker
    try:
        print("\nGetting initial balance...")
        balance_info = exchange.get_balance()
        print(f"Balance info: {balance_info}")
        
        # Get the USDT balance
        usdt_balance = 0.0
        for acc in balance_info if isinstance(balance_info, list) else [balance_info]:
            if isinstance(acc, dict) and acc.get('marginCoin') == 'USDT':
                usdt_balance = float(acc.get('available', 0))
                break
        
        print(f"Available USDT balance: {usdt_balance}")
        
        # Initialize DailyLossTracker
        max_daily_loss_percentage = 0.03  # 3% daily loss threshold
        tracker = DailyLossTracker(max_daily_loss_percentage)
        tracker.update_starting_balance(usdt_balance)
        
        print(f"Daily loss tracker initialized with max loss: {max_daily_loss_percentage*100}%")
        print(f"Starting balance: {usdt_balance}")
        
        # Test updating P&L
        print("\nTesting P&L updates...")
        
        # Simulate some P&L changes
        test_pnl_values = [-10.5, -15.2, 5.0, -8.7, 12.3]
        
        for i, pnl in enumerate(test_pnl_values):
            tracker.update_pnl(pnl)
            daily_pnl = tracker.get_daily_pnl()
            daily_loss_pct = tracker.get_daily_loss_percentage()
            circuit_breaker_active = tracker.is_circuit_breaker_active()
            
            print(f"Step {i+1}: P&L = {pnl:+.2f}, Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
        
        # Test with a large loss to trigger circuit breaker
        print("\nTesting circuit breaker with large loss...")
        large_loss = -(usdt_balance * 0.02)  # 2% of balance as loss
        tracker.update_pnl(large_loss)
        daily_pnl = tracker.get_daily_pnl()
        daily_loss_pct = tracker.get_daily_loss_percentage()
        circuit_breaker_active = tracker.is_circuit_breaker_active()
        
        print(f"After large loss ({large_loss:.2f}): Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
        
        print("DailyLossTracker test completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_multiple_trades():
    print("\n=== Testing DailyLossTracker with Simulated Trades ===")
    
    # Initialize with mock starting balance
    max_daily_loss_percentage = 0.03  # 3% daily loss threshold
    tracker = DailyLossTracker(max_daily_loss_percentage)
    starting_balance = 1000.0  # Mock starting balance
    tracker.update_starting_balance(starting_balance)
    
    print(f"Mock starting balance: {starting_balance}")
    
    # Simulate multiple trades (some winners, some losers)
    trades = [
        {'id': 'trade_1', 'pnl': 25.50, 'type': 'profit'},
        {'id': 'trade_2', 'pnl': -18.75, 'type': 'loss'},
        {'id': 'trade_3', 'pnl': 12.30, 'type': 'profit'},
        {'id': 'trade_4', 'pnl': -45.20, 'type': 'loss'},
        {'id': 'trade_5', 'pnl': 8.90, 'type': 'profit'},
    ]
    
    for trade in trades:
        tracker.update_pnl(trade['pnl'])
        daily_pnl = tracker.get_daily_pnl()
        daily_loss_pct = tracker.get_daily_loss_percentage()
        circuit_breaker_active = tracker.is_circuit_breaker_active()
        
        print(f"{trade['id']}: P&L = {trade['pnl']:+.2f} ({trade['type']}), Daily P&L = {daily_pnl:+.2f}, Loss % = {daily_loss_pct*100:.2f}%, Circuit Breaker = {circuit_breaker_active}")
        
        time.sleep(0.1)  # Small delay to simulate real trading
    
    print("Simulation completed!")
    
    # Test reset functionality
    print("\nTesting daily reset...")
    # This would normally happen automatically at the reset time
    current_time = datetime.now().timestamp()
    print(f"Current time: {datetime.fromtimestamp(current_time)}")
    print(f"Reset time: {datetime.fromtimestamp(tracker.reset_time)}")
    print(f"Time to reset: {tracker.reset_time - current_time:.2f} seconds")
    
    if current_time >= tracker.reset_time:
        tracker.reset_daily_counter()
        print("Counter reset manually")
    else:
        print("Counter would reset at scheduled time")
    
    return True

if __name__ == "__main__":
    print("Testing DailyLossTracker class")
    print(f"Current time: {datetime.now()}")
    
    success = test_daily_loss_tracker()
    success = test_with_multiple_trades() and success
    
    if success:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed!")
        sys.exit(1)