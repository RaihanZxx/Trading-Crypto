import os
import threading
import time
import toml
from typing import Dict, Optional
from connectors.exchange_service import BitgetExchangeService


class TradeManager:
    def __init__(self):
        self.exchange = BitgetExchangeService(
            api_key=os.getenv('BITGET_API_KEY'),
            secret_key=os.getenv('BITGET_SECRET_KEY'),
            passphrase=os.getenv('BITGET_PASSPHRASE')
        )
        
        # Load configuration from config.toml
        self._load_config()
        
        self.active_positions = {} # Lacak posisi aktif
        self.lock = threading.Lock()

    def _load_config(self):
        """Load configuration from config.toml"""
        possible_paths = [
            "config/config.toml",           # Relative to current working directory
            "../config/config.toml",        # From src directory to root
            "../../config/config.toml",     # Additional possible path
        ]
        
        config_data = None
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    config_data = toml.load(f)
                break
        
        if config_data is None:
            raise ValueError("config.toml file is required and must contain execution parameters")
        
        # Extract execution parameters from config
        try:
            execution_config = config_data.get('execution', {})
            
            self.max_concurrent_positions = execution_config['max_concurrent_positions']
            self.stop_loss_percent = execution_config['stop_loss_percent']
            self.risk_percentage = execution_config['risk_percentage']
            self.use_dynamic_risk = execution_config['use_dynamic_risk']
            
            # Validate loaded values
            if self.max_concurrent_positions <= 0:
                raise ValueError("max_concurrent_positions must be positive")
            if self.stop_loss_percent <= 0 or self.stop_loss_percent >= 1:
                raise ValueError("stop_loss_percent must be between 0 and 1")
            if self.risk_percentage <= 0 or self.risk_percentage >= 1:
                raise ValueError("risk_percentage must be between 0 and 1")
                
        except KeyError as e:
            raise ValueError(f"Missing required execution parameter in config.toml: {e}")

    def _can_open_new_position(self) -> bool:
        """Cek apakah kita bisa membuka posisi baru berdasarkan batasan."""
        with self.lock:
            return len(self.active_positions) < self.max_concurrent_positions

    def _calculate_position_size(self, price: float) -> float:
        """Hitung ukuran posisi dalam satuan koin."""
        # Dynamic risk: percentage of total wallet balance
        wallet_balance = self._get_wallet_balance()
        if wallet_balance is not None:
            # Calculate max risk amount (1% of balance)
            risk_amount = wallet_balance * self.risk_percentage
        else:
            raise ValueError("Could not fetch wallet balance for risk calculation")
        
        # Calculate position size in contracts to ensure risk = risk_amount
        # Risk = Position_Size * Price * Stop_Loss_Percentage
        # Position_Size = Risk / (Price * Stop_Loss_Percentage)
        position_size = risk_amount / (price * self.stop_loss_percent)
        
        # Ensure minimum size based on exchange requirements
        minimum_size = 0.001  # Adjust according to exchange minimum
        position_size = max(position_size, minimum_size)
        
        return round(position_size, 3)  # Bulatkan ke 3 desimal

    def _get_wallet_balance(self) -> Optional[float]:
        """Get the current wallet balance."""
        try:
            # Get balance data from exchange - returns list of account balances
            balance_data = self.exchange.get_balance("USDT")
            
            # If balance_data is a list, find the USDT account
            if isinstance(balance_data, list):
                for account in balance_data:
                    if account.get('marginCoin') == 'USDT':
                        equity = account.get('accountEquity')
                        return float(equity) if equity else 0.0
                # If no USDT account found in list, return 0
                return 0.0
            # If balance_data is a single account dictionary
            elif isinstance(balance_data, dict):
                equity = balance_data.get('accountEquity')
                return float(equity) if equity else 0.0
            else:
                return 0.0
        except Exception as e:
            print(f"[Python Executor] Error getting wallet balance: {e}")
            return None

    def get_active_positions(self) -> Dict:
        """Get all active positions."""
        with self.lock:
            return self.active_positions.copy()

    def get_position_summary(self) -> Dict:
        """Get summary of all active positions and risk metrics."""
        positions = self.get_active_positions()
        total_risk = 0.0
        total_positions = len(positions)
        
        wallet_balance = self._get_wallet_balance()
        
        for symbol, pos_data in positions.items():
            # Calculate risk for this position: position_size * entry_price * stop_loss_percent
            risk_amount = abs(pos_data['size'] * pos_data['entry_price'] * self.stop_loss_percent)
            total_risk += risk_amount
            
        return {
            "total_positions": total_positions,
            "max_concurrent_positions": self.max_concurrent_positions,
            "total_at_risk": total_risk,
            "wallet_balance": wallet_balance,
            "risk_percentage_of_balance": (total_risk / wallet_balance * 100) if wallet_balance and wallet_balance > 0 else 0,
            "risk_per_position_limit": self.risk_percentage
        }

    def close_position(self, symbol: str, close_all: bool = True) -> Dict:
        """Manually close a specific position."""
        try:
            with self.lock:
                if symbol not in self.active_positions:
                    # Check if position exists on exchange even if not in our tracking
                    try:
                        exchange_positions = self.exchange.get_positions(symbol)
                        position_exists = any(pos.get('symbol') == symbol and float(pos.get('totalPos', 0)) != 0 for pos in exchange_positions)
                        if not position_exists:
                            return {"status": "error", "reason": f"No active position for {symbol}"}
                        else:
                            # Position exists on exchange but not in our tracking - just close it
                            pass
                    except Exception:
                        return {"status": "error", "reason": f"No active position for {symbol} in local tracking"}
            
            # Get the actual position details from exchange to determine size and side
            try:
                exchange_positions = self.exchange.get_positions(symbol)
                position = next((pos for pos in exchange_positions if pos.get('symbol') == symbol), None)
                if not position:
                    return {"status": "error", "reason": f"No position found for {symbol} on exchange"}
                
                # Determine position size and side
                position_size_str = position.get('totalPos', '0')
                position_size = abs(float(position_size_str)) if position_size_str else 0.0
                hold_side = position.get('holdSide', '').lower()
                
                if position_size <= 0:
                    # Position already closed
                    with self.lock:
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                    return {"status": "success", "message": f"Position {symbol} was already closed"}
                
                # Determine the side to close the position
                # holdSide is typically 'long' or 'short'
                close_side = "buy" if hold_side == "short" else "sell"
                
            except Exception as e:
                print(f"[Python Executor] Error getting position details from exchange for {symbol}: {e}")
                # If we can't get exchange position details, use local tracking if available
                with self.lock:
                    if symbol in self.active_positions:
                        position_data = self.active_positions[symbol]
                        position_size = position_data['size']
                        close_side = "sell" if position_data['side'] == "buy" else "buy"
                    else:
                        return {"status": "error", "reason": f"Unable to determine position details for {symbol}"}
            
            # Place market order to close the position
            order_result = self.exchange.place_order(
                symbol=symbol,
                side=close_side,
                size=position_size,
                order_type="market"
            )
            
            if 'orderId' in order_result:
                # Remove from active positions if it exists in our tracking
                with self.lock:
                    if symbol in self.active_positions:
                        del self.active_positions[symbol]
                return {
                    "status": "success", 
                    "message": f"Position {symbol} closed successfully",
                    "order_id": order_result['orderId']
                }
            else:
                return {"status": "error", "reason": "Failed to close position via market order"}
                
        except Exception as e:
            print(f"[Python Executor] Error closing position {symbol}: {e}")
            return {"status": "error", "reason": str(e)}

    def execute_trade(self, signal: Dict):
        """Fungsi yang dipanggil dari Rust untuk mengeksekusi trade."""
        print(f"[Python Executor] Menerima sinyal untuk {signal['symbol']}")
        
        if not self._can_open_new_position():
            print(f"[Python Executor] Gagal: Posisi maksimum ({self.max_concurrent_positions}) tercapai.")
            return {"status": "error", "reason": "Max positions reached"}

        symbol = signal['symbol']
        price = signal['price']
        signal_type = signal['signal_type'] # Misal "StrongBuy" atau "StrongSell"
        
        side = "buy" if "Buy" in signal_type else "sell"
        
        position_size = self._calculate_position_size(price)
        
        print(f"[Python Executor] Menempatkan order {side.upper()} untuk {position_size} {symbol} @ {price}")
        
        try:
            # Place the main market order
            order_result = self.exchange.place_order(
                symbol=symbol,
                side=side,
                size=position_size,
                order_type="market"  # Using market for immediate execution
            )
            
            if not order_result or 'orderId' not in order_result:
                print(f"[Python Executor] Failed to place order for {symbol}")
                return {"status": "error", "reason": "Order placement failed"}
            
            order_id = order_result['orderId']
            print(f"[Python Executor] Order placed successfully: {order_id}")
            
            # Calculate stop loss price based on signal type
            if "Buy" in signal_type:
                # For long positions, stop loss is below entry price
                stop_loss_price = price * (1 - self.stop_loss_percent)
            else:
                # For short positions, stop loss is above entry price
                stop_loss_price = price * (1 + self.stop_loss_percent)
            
            # Place stop loss order
            stop_order_result = self.exchange.place_stop_market_order(
                symbol=symbol,
                side="sell" if side == "buy" else "buy",  # Close the position
                trigger_price=stop_loss_price,
                size=position_size,
                trigger_type="market_price"
            )
            
            if not stop_order_result or 'orderId' not in stop_order_result:
                print(f"[Python Executor] Failed to place stop loss order for {symbol}")
                return {"status": "error", "reason": "Stop loss order placement failed"}
            
            stop_order_id = stop_order_result['orderId']
            print(f"[Python Executor] Stop loss order placed: {stop_order_id} at {stop_loss_price}")
            
            # Track the position with entry price, size, stop loss price, and order IDs
            with self.lock:
                self.active_positions[symbol] = {
                    "entry_price": price,
                    "size": position_size,
                    "side": side,
                    "stop_loss_price": stop_loss_price,
                    "main_order_id": order_id,
                    "stop_order_id": stop_order_id,
                    "position_id": order_result.get('orderId', ''),  # Using main order ID as position ID
                    "timestamp": signal['timestamp']
                }
            
            print(f"[Python Executor] Position tracked for {symbol}: {self.active_positions[symbol]}")
            
            # Start a monitoring thread for this position
            monitoring_thread = threading.Thread(
                target=self._monitor_position, 
                args=(symbol,), 
                daemon=True
            )
            monitoring_thread.start()
            
            return {
                "status": "success", 
                "symbol": symbol, 
                "size": position_size,
                "entry_price": price,
                "stop_loss_price": stop_loss_price,
                "main_order_id": order_id,
                "stop_order_id": stop_order_id
            }
            
        except Exception as e:
            print(f"[Python Executor] Error executing trade for {symbol}: {e}")
            return {"status": "error", "reason": str(e)}
    
    def _monitor_position(self, symbol: str):
        """
        Internal method to monitor a specific position.
        This method is called by execute_trade to start monitoring for a position.
        """
        monitor = PositionMonitor(self)
        monitor.monitor_position(symbol)


class PositionMonitor:
    def __init__(self, trade_manager):
        self.trade_manager = trade_manager
        self.monitoring_active = True
    
    def _check_position_status(self, symbol: str) -> bool:
        """Check if position still exists or has been closed."""
        try:
            positions = self.trade_manager.exchange.get_positions(symbol)
            
            # Check if the position still exists in the exchange
            for position in positions:
                if position.get('symbol') == symbol:
                    # If position size is 0, it means position is closed
                    position_size_str = position.get('totalPos', '0')
                    if position_size_str is None:
                        position_size_str = '0'
                    position_size = float(position_size_str)
                    if position_size == 0:
                        print(f"[Monitor] Position for {symbol} is closed (size: {position_size})")
                        return False
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
            print(f"[Monitor] Position for {symbol} not found in active positions")
            return True
        
        # Check if position still exists on exchange
        return not self._check_position_status(symbol)
    
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.monitoring_active = False
    
    def monitor_position(self, symbol: str):
        """Monitor a specific position for stop loss or other conditions."""
        print(f"[Monitor] Starting monitoring for position: {symbol}")
        
        while self.monitoring_active and symbol in self.trade_manager.active_positions:
            try:
                # Check if position should be closed
                if self._should_close_position(symbol):
                    # Remove position from active positions
                    with self.trade_manager.lock:
                        if symbol in self.trade_manager.active_positions:
                            del self.trade_manager.active_positions[symbol]
                            print(f"[Monitor] Removed {symbol} from active positions")
                    
                    print(f"[Monitor] Stopped monitoring for {symbol}")
                    break
                
                # Sleep for a while before next check
                # Use smaller intervals to allow faster response to stop_monitoring
                sleep_remaining = 30
                while sleep_remaining > 0 and self.monitoring_active:
                    time.sleep(min(5, sleep_remaining))  # Wake up every 5 seconds to check if should stop
                    sleep_remaining -= 5
                
                if not self.monitoring_active:
                    print(f"[Monitor] Monitoring stopped externally for {symbol}")
                    break
                
            except Exception as e:
                print(f"[Monitor] Error monitoring position {symbol}: {e}")
                # Brief pause before retrying, but respect the stop flag
                sleep_remaining = 10
                while sleep_remaining > 0 and self.monitoring_active:
                    time.sleep(min(2, sleep_remaining))
                    sleep_remaining -= 2
        
        print(f"[Monitor] Monitoring thread for {symbol} ended")


# Buat instance global agar bisa diakses dari Rust
trade_manager = TradeManager()


def handle_trade_signal(signal: Dict):
    """Wrapper fungsi sederhana untuk dipanggil dari Rust."""
    return trade_manager.execute_trade(signal)