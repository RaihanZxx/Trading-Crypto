import time
import threading
from typing import Dict, Optional


class PositionMonitor:
    def __init__(self, trade_manager):
        self.trade_manager = trade_manager
        self.monitoring_active = True
    
    def _check_position_status(self, symbol: str) -> bool:
        """Check if position still exists or has been closed."""
        try:
            positions = self.trade_manager.exchange.get_positions(symbol)
            print(f"[Monitor] Checking position status for {symbol}, got {len(positions)} positions from exchange")
            
            # Check if the position still exists in the exchange
            for position in positions:
                if position.get('symbol') == symbol:
                    # Check multiple possible field names for position size based on Bitget API response
                    # Prioritize 'total' and 'available' which were found in actual API response
                    position_size_str = position.get('total', '0')  # Primary field from API response
                    if position_size_str == '0' or position_size_str is None:
                        available_size = position.get('available', '0')  # Alternative field
                        if available_size != '0':
                            position_size_str = available_size
                        else:
                            # Try to calculate from other fields if possible
                            open_delegate_size = position.get('openDelegateSize', '0')
                            if open_delegate_size != '0':
                                position_size_str = open_delegate_size
                            else:
                                position_size_str = '0'
                    
                    # Ensure we have a valid string
                    if position_size_str is None:
                        position_size_str = '0'
                    
                    # Convert to float and check if position is still open
                    try:
                        position_size = float(position_size_str)
                    except ValueError:
                        position_size = 0.0  # Default to 0 if conversion fails
                    
                    # Use correct field names from Bitget API response
                    avg_open_price = position.get('openPriceAvg', 'N/A')  # Correct field name from API
                    unrealized_pnl = position.get('unrealizedPL', 'N/A')  # Correct field name from API
                    
                    if position_size == 0:
                        print(f"[Monitor] Position for {symbol} is closed (size: {position_size}, avgOpenPrice: {avg_open_price}, unrealizedPnl: {unrealized_pnl})")
                        return False
                    else:
                        print(f"[Monitor] Position for {symbol} is still open (size: {position_size}, avgOpenPrice: {avg_open_price}, unrealizedPnl: {unrealized_pnl})")
                    return True
            
            # If no position found, assume it's closed
            print(f"[Monitor] No position found for {symbol}, assuming closed")
            return False
        except Exception as e:
            print(f"[Monitor] Error checking position status for {symbol}: {e}")
            # In case of error, don't remove - let other checks handle it
            return True
    
    def _should_close_position(self, symbol: str) -> bool:
        """Check if position should be closed based on monitoring criteria."""
        # Check if the symbol still exists in active positions
        if symbol not in self.trade_manager.active_positions:
            print(f"[Monitor] Position for {symbol} not found in active positions - position may have been manually closed or reached target")
            return True
        
        # Check if position still exists on exchange
        position_exists = self._check_position_status(symbol)
        print(f"[Monitor] Position exists check for {symbol}: {position_exists}")
        return not position_exists
    
    def _update_trailing_stop(self, symbol: str):
        """Update trailing stop loss based on current price movement."""
        try:
            # Get current position data from local tracking
            with self.trade_manager.lock:
                if symbol not in self.trade_manager.active_positions:
                    return
            
            position_data = self.trade_manager.active_positions[symbol]
            entry_price = position_data.get('entry_price')
            current_side = position_data.get('side')  # 'buy' for long, 'sell' for short
            current_sl = position_data.get('stop_loss_price')
            
            # Get current market price
            ticker_data = self.trade_manager.exchange.get_ticker(symbol)
            if 'lastPr' in ticker_data:
                current_price = float(ticker_data['lastPr'])
            elif 'last' in ticker_data:
                current_price = float(ticker_data['last'])
            elif isinstance(ticker_data, list) and len(ticker_data) > 0 and 'lastPr' in ticker_data[0]:
                current_price = float(ticker_data[0]['lastPr'])
            else:
                print(f"[Monitor] Could not get current price for {symbol}")
                return
            
            # Only update trailing stop if position is profitable
            should_update_sl = False
            new_sl_price = None
            
            if current_side == 'buy':  # Long position
                # For long positions, if price moved up significantly, move SL up
                if current_price > entry_price and current_price > current_sl * 1.005:  # Only update if price moved 0.5% above current SL
                    # Move stop loss to lock in some profit (e.g., 0.3% below current price)
                    new_sl_price = current_price * (1 - self.trade_manager.stop_loss_percent * 0.6)  # Use 60% of original stop loss percentage
                    if new_sl_price > current_sl:  # Only move SL up, never down
                        should_update_sl = True
            elif current_side == 'sell':  # Short position
                # For short positions, if price moved down significantly, move SL down
                if current_price < entry_price and current_price < current_sl * 0.995:  # Only update if price moved 0.5% below current SL
                    # Move stop loss to lock in some profit (e.g., 0.3% above current price)
                    new_sl_price = current_price * (1 + self.trade_manager.stop_loss_percent * 0.6)  # Use 60% of original stop loss percentage
                    if new_sl_price < current_sl:  # Only move SL down, never up
                        should_update_sl = True
            
            if should_update_sl:
                print(f"[Monitor] Updating trailing stop for {symbol}: from {current_sl} to {new_sl_price}")
                result = self.trade_manager.update_position_sl_tp(symbol, new_stop_loss_price=new_sl_price)
                if result.get('status') == 'success':
                    print(f"[Monitor] Trailing stop updated successfully for {symbol}")
                else:
                    print(f"[Monitor] Failed to update trailing stop for {symbol}: {result.get('reason')}")
                    
        except Exception as e:
            print(f"[Monitor] Error updating trailing stop for {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.monitoring_active = False
    
    def monitor_position(self, symbol: str):
        """Monitor a specific position for stop loss or other conditions."""
        print(f"[Monitor] Starting monitoring for position: {symbol}")
        
        # Log initial position details
        with self.trade_manager.lock:
            if symbol in self.trade_manager.active_positions:
                pos_data = self.trade_manager.active_positions[symbol]
                print(f"[Monitor] Initial position data for {symbol}: size={pos_data.get('size')}, entry_price={pos_data.get('entry_price')}, side={pos_data.get('side')}, stop_loss_price={pos_data.get('stop_loss_price')}, timestamp={pos_data.get('timestamp')}")
        
        while self.monitoring_active and symbol in self.trade_manager.active_positions:
            try:
                print(f"[Monitor] Monitoring cycle started for {symbol}")
                
                # Check if position should be closed
                if self._should_close_position(symbol):
                    # Get position details before removal for logging
                    pos_details = None
                    with self.trade_manager.lock:
                        if symbol in self.trade_manager.active_positions:
                            pos_details = self.trade_manager.active_positions[symbol].copy()
                            del self.trade_manager.active_positions[symbol]
                            print(f"[Monitor] Removed {symbol} from active positions - reason: position closed on exchange or not found")
                    
                    # Persist the change to file
                    self.trade_manager.save_persisted_positions()
                    
                    # Log why the position was removed
                    if pos_details:
                        print(f"[Monitor] Position details for {symbol} at removal: size={pos_details.get('size')}, entry_price={pos_details.get('entry_price')}, side={pos_details.get('side')}, stop_loss_price={pos_details.get('stop_loss_price')}")
                    
                    print(f"[Monitor] Stopped monitoring for {symbol}")
                    break
                
                # Update trailing stop loss if applicable
                self._update_trailing_stop(symbol)
                
                # Sleep for a while before next check
                # Use smaller intervals to allow faster response to stop_monitoring
                sleep_remaining = 30
                print(f"[Monitor] Sleeping for {sleep_remaining} seconds before next check for {symbol}")
                while sleep_remaining > 0 and self.monitoring_active:
                    time.sleep(min(5, sleep_remaining))  # Wake up every 5 seconds to check if should stop
                    sleep_remaining -= 5
                
                if not self.monitoring_active:
                    print(f"[Monitor] Monitoring stopped externally for {symbol}")
                    break
                
            except Exception as e:
                print(f"[Monitor] Error monitoring position {symbol}: {e}")
                import traceback
                traceback.print_exc()
                # Brief pause before retrying, but respect the stop flag
                sleep_remaining = 10
                while sleep_remaining > 0 and self.monitoring_active:
                    time.sleep(min(2, sleep_remaining))
                    sleep_remaining -= 2
        
        print(f"[Monitor] Monitoring thread for {symbol} ended")