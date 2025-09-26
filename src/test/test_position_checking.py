import os
import sys
import time
import threading
from datetime import datetime

# Tambahkan path untuk mengakses module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from execution_service.manager import PositionMonitor
from connectors.exchange_service import BitgetExchangeService

def test_position_checking():
    print("=== Testing Position Checking Logic ===")
    print(f"Current time: {datetime.now()}")
    
    # Load environment variables
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        print("Environment variables not set. Please set BITGET_API_KEY, BITGET_SECRET_KEY, and BITGET_PASSPHRASE")
        return False
    
    print("API credentials loaded")
    
    # Initialize exchange service
    exchange = BitgetExchangeService(api_key, secret_key, passphrase)
    
    # Get current positions to understand structure
    try:
        print("\nGetting current positions from exchange...")
        current_positions = exchange.get_positions()
        print(f"Total positions returned: {len(current_positions)}")
        
        if current_positions:
            for i, pos in enumerate(current_positions):
                print(f"Position {i+1}: {pos}")
        else:
            print("No positions currently open on exchange")
        
        # Test checking specific symbol
        if current_positions:
            # Use first symbol as test
            test_symbol = current_positions[0].get('symbol', 'BTCUSDT')
        else:
            # Use a common symbol for testing if no positions
            test_symbol = 'BTCUSDT'
        
        print(f"\nTesting position check for symbol: {test_symbol}")
        
        # Get positions for specific symbol
        symbol_positions = exchange.get_positions(test_symbol)
        print(f"Positions for {test_symbol}: {symbol_positions}")
        
        if symbol_positions:
            for pos in symbol_positions:
                symbol = pos.get('symbol')
                total_pos = pos.get('totalPos', '0')
                avg_open_price = pos.get('avgOpenPrice', 'N/A')
                hold_side = pos.get('holdSide', 'N/A')
                unrealized_pnl = pos.get('unrealizedPnl', 'N/A')
                
                print(f"  Symbol: {symbol}")
                print(f"  TotalPos: {total_pos}")
                print(f"  AvgOpenPrice: {avg_open_price}")
                print(f"  HoldSide: {hold_side}")
                print(f"  UnrealizedPnl: {unrealized_pnl}")
                print(f"  Pos Size as Float: {float(total_pos) if total_pos else 0}")
        
        # Test the exact logic from _check_position_status
        print(f"\nTesting the exact logic used in _check_position_status:")
        print(f"Checking if position for {test_symbol} exists based on exchange API response...")
        
        positions = exchange.get_positions(test_symbol)
        print(f"Got {len(positions)} positions from exchange for {test_symbol}")
        
        position_exists = False
        for position in positions:
            print(f"Position data: {position}")
            if position.get('symbol') == test_symbol:
                position_size_str = position.get('totalPos', '0')
                if position_size_str is None:
                    position_size_str = '0'
                position_size = float(position_size_str)
                
                print(f"Position size: {position_size} (from '{position_size_str}')")
                
                if position_size == 0:
                    print(f"Position size is 0, considering position as closed")
                else:
                    print(f"Position size is {position_size}, considering position as still open")
                    position_exists = True
                break
        
        if not position_exists and len(positions) > 0:
            print(f"Position for {test_symbol} not found in exchange response")
            position_exists = False
        
        print(f"Final result: Position for {test_symbol} exists = {position_exists}")
        
        # Test with a position that doesn't exist (or one with zero size)
        print(f"\nTesting the condition that causes removal - checking position_exists={position_exists}")
        should_close = not position_exists
        print(f"_should_close_position would return: {should_close}")
        
        if should_close:
            print("⚠️  This would cause the position to be removed from active_positions!")
            print("   Even if the position actually exists on the exchange!")
        
        print("\n✅ Position checking test completed")
        return True
        
    except Exception as e:
        print(f"Error during position checking test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_timing_issue():
    print("\n=== Testing Potential Timing Issue ===")
    
    # Load environment variables
    api_key = os.getenv('BITGET_API_KEY')
    secret_key = os.getenv('BITGET_SECRET_KEY')
    passphrase = os.getenv('BITGET_PASSPHRASE')
    
    if not all([api_key, secret_key, passphrase]):
        print("Environment variables not set. Please set BITGET_API_KEY, BITGET_SECRET_KEY, and BITGET_PASSPHRASE")
        return False
    
    # Initialize exchange service
    exchange = BitgetExchangeService(api_key, secret_key, passphrase)
    
    # Test with a symbol that we might have a position in
    test_symbol = "BTCUSDT"  # Common symbol for testing
    
    print(f"Testing for potential timing issue with {test_symbol}")
    
    # Get positions multiple times quickly to see if there are inconsistencies
    for i in range(3):
        try:
            positions1 = exchange.get_positions(test_symbol)
            time.sleep(0.5)  # Small delay
            positions2 = exchange.get_positions(test_symbol)
            
            print(f"Check {i+1}: First call returned {len(positions1)} positions, Second call returned {len(positions2)} positions")
            
            if len(positions1) != len(positions2):
                print(f"  ⚠️  Inconsistency detected! API responses differ between calls")
            else:
                # Check if content is the same
                for p1, p2 in zip(positions1, positions2):
                    if p1 != p2:
                        print(f"  ⚠️  Position data changed between calls: {p1} vs {p2}")
                        break
            
            time.sleep(1)  # Wait before next check
            
        except Exception as e:
            print(f"Error during timing test: {e}")
            continue
    
    print("✅ Timing issue test completed")
    return True

if __name__ == "__main__":
    print("Testing position checking logic that may cause premature position removal")
    
    success1 = test_position_checking()
    success2 = test_timing_issue()
    
    if success1 and success2:
        print("\n🎉 Position checking tests completed!")
        print("\n🔍 Summary of potential issue:")
        print("   The _check_position_status function might incorrectly determine that")
        print("   a position doesn't exist if:")
        print("   1. There's a delay between position opening and exchange API update")
        print("   2. The API response structure is different than expected")
        print("   3. Position size is temporarily reported as 0 during updates")
        print("   4. The symbol name format differs between local tracking and exchange API")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)