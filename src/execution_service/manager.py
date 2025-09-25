import os
import threading
import time
import json
import toml
import os
import threading
import time
import json
import toml
from typing import Dict, Optional
from connectors.exchange_service import BitgetExchangeService


class PortfolioRiskTracker:
    """Tracks portfolio-level risk metrics."""
    def __init__(self, max_portfolio_risk: float = 0.05):  # 5% max portfolio risk
        self.max_portfolio_risk = max_portfolio_risk
        self.lock = threading.Lock()
    
    def check_portfolio_risk(self, current_positions_value: float, total_balance: float) -> tuple[bool, str]:
        """
        Check if opening a new position would exceed portfolio risk limits.
        Returns (is_safe, reason_message)
        """
        if total_balance <= 0:
            return False, "Total balance is zero or negative"
        
        portfolio_risk_percentage = current_positions_value / total_balance
        
        if portfolio_risk_percentage > self.max_portfolio_risk:
            return False, f"Portfolio risk would exceed {self.max_portfolio_risk*100:.2f}% (current: {portfolio_risk_percentage*100:.2f}%)"
        
        return True, "Portfolio risk within acceptable limits"


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
        from datetime import datetime, timedelta, timezone
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
            return abs(self.daily_pnl) / self.start_balance if self.start_balance > 0 else False
    
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
        
        # Portfolio-level risk tracking
        self.portfolio_risk_tracker = PortfolioRiskTracker(
            max_portfolio_risk=self.max_portfolio_risk_percentage
        )
        
        # Cache saldo
        self.wallet_balance_cache = None
        self.balance_last_updated = 0
        self.BALANCE_CACHE_DURATION = 30  # Cache saldo selama 30 detik
        
        # Circuit breaker state
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        self.circuit_breaker_lock = threading.Lock()
        self.circuit_breaker_reset_time = time.time() + self.max_circuit_breaker_duration
        self.daily_loss_limit = self.max_daily_loss_percentage  # Maximum daily portfolio loss allowed
        self.daily_loss_tracker = DailyLossTracker(self.daily_loss_limit)
        
        # Position state persistence
        self.positions_file = "data/active_positions.json"
        self._ensure_data_directory()
        self._load_persisted_positions()

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
            self.max_portfolio_risk_percentage = execution_config.get('max_portfolio_risk_percentage', 0.05)  # 5% default
            self.max_daily_loss_percentage = execution_config.get('max_daily_loss_percentage', 0.03)  # 3% default
            self.max_circuit_breaker_duration = execution_config.get('max_circuit_breaker_duration', 3600)  # 1 hour default
            self.max_price_deviation_percent = execution_config.get('max_price_deviation_percent', 0.2)  # 0.2% default
            self.paper_trading = execution_config.get('paper_trading', False)
            
            # Validate loaded values
            if self.max_concurrent_positions <= 0:
                raise ValueError("max_concurrent_positions must be positive")
            if self.stop_loss_percent <= 0 or self.stop_loss_percent >= 1:
                raise ValueError("stop_loss_percent must be between 0 and 1")
            if self.risk_percentage <= 0 or self.risk_percentage >= 1:
                raise ValueError("risk_percentage must be between 0 and 1")
            if self.max_portfolio_risk_percentage <= 0 or self.max_portfolio_risk_percentage > 1:
                raise ValueError("max_portfolio_risk_percentage must be between 0 and 1")
            if self.max_daily_loss_percentage <= 0 or self.max_daily_loss_percentage > 1:
                raise ValueError("max_daily_loss_percentage must be between 0 and 1")
            if self.max_circuit_breaker_duration <= 0:
                raise ValueError("max_circuit_breaker_duration must be positive")
                
        except KeyError as e:
            raise ValueError(f"Missing required execution parameter in config.toml: {e}")
    
    def _ensure_data_directory(self):
        """Create data directory if it doesn't exist."""
        data_dir = os.path.dirname(self.positions_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
    
    def _load_persisted_positions(self):
        """Load persisted active positions from file at startup."""
        try:
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r') as f:
                    persisted_positions = json.load(f)
                    
                # Convert string keys back to appropriate types if needed
                with self.lock:
                    self.active_positions = persisted_positions
                    print(f"[Python Executor] Loaded {len(self.active_positions)} persisted positions from {self.positions_file}")
                
                # Restart monitoring for each loaded position
                for symbol in self.active_positions:
                    print(f"[Python Executor] Restarting monitoring for persisted position: {symbol}")
                    monitoring_thread = threading.Thread(
                        target=self._monitor_position, 
                        args=(symbol,), 
                        daemon=True
                    )
                    monitoring_thread.start()
                    print(f"[Python Executor] Resumed monitoring thread for {symbol}")
            else:
                print(f"[Python Executor] Positions file {self.positions_file} not found. Starting with empty positions.")
        except Exception as e:
            print(f"[Python Executor] Error loading persisted positions: {e}")
            # If there's an error loading, start with empty positions
            with self.lock:
                self.active_positions = {}
    
    def _save_persisted_positions(self):
        """Save active positions to file."""
        try:
            with self.lock:
                # Create a copy to avoid holding the lock during file I/O
                positions_to_save = self.active_positions.copy()
            
            with open(self.positions_file, 'w') as f:
                json.dump(positions_to_save, f, indent=2)
                
            print(f"[Python Executor] Saved {len(positions_to_save)} active positions to {self.positions_file}")
        except Exception as e:
            print(f"[Python Executor] Error saving positions to file: {e}")

    def _can_open_new_position(self) -> bool:
        """Cek apakah kita bisa membuka posisi baru berdasarkan batasan."""
        with self.lock:
            return len(self.active_positions) < self.max_concurrent_positions

    def _calculate_position_size(self, price: float) -> float:
        """Hitung ukuran posisi dalam satuan koin."""
        with self.lock:  # Tambahkan lock di sini
            # Dynamic risk: percentage of total wallet balance
            wallet_balance = self._get_wallet_balance()  # _get_wallet_balance tidak perlu lock jika dipanggil dari sini
            if wallet_balance is not None and wallet_balance > 0:
                # Calculate max risk amount (1% of balance)
                risk_amount = wallet_balance * self.risk_percentage
            else:
                raise ValueError("Could not fetch wallet balance or balance is zero")
            
            # Calculate position size in contracts to ensure risk = risk_amount
            # Risk = Position_Size * Price * Stop_Loss_Percentage
            # Position_Size = Risk / (Price * Stop_Loss_Percentage)
            position_size = risk_amount / (price * self.stop_loss_percent)
            
            # Ensure minimum size based on exchange requirements
            minimum_size = 0.001  # Adjust according to exchange minimum
            position_size = max(position_size, minimum_size)
            
            return round(position_size, 3)  # Bulatkan ke 3 desimal

    def _calculate_active_positions_value(self) -> float:
        """Calculate the total value of all active positions."""
        total_value = 0.0
        with self.lock:
            for symbol, position_data in self.active_positions.items():
                try:
                    # Get current price for the symbol
                    current_price_data = self.exchange.get_ticker(symbol)
                    current_price = None
                    if 'last' in current_price_data:
                        current_price = float(current_price_data['last'])
                    elif 'lastPr' in current_price_data:
                        current_price = float(current_price_data['lastPr'])
                    elif isinstance(current_price_data, list) and len(current_price_data) > 0 and 'lastPr' in current_price_data[0]:
                        current_price = float(current_price_data[0]['lastPr'])
                    
                    if current_price is not None:
                        # Calculate position value (size * current_price)
                        position_value = abs(position_data['size'] * current_price)
                        total_value += position_value
                except Exception as e:
                    print(f"[Python Executor] Error calculating position value for {symbol}: {e}")
                    # If we can't get the current price, use entry price as approximation
                    position_value = abs(position_data['size'] * position_data['entry_price'])
                    total_value += position_value
        
        return total_value

    def _get_wallet_balance(self) -> Optional[float]:
        """Get the current wallet balance."""
        now = time.time()
        # Gunakan cache jika masih valid
        if self.wallet_balance_cache is not None and (now - self.balance_last_updated) < self.BALANCE_CACHE_DURATION:
            print("[Python Executor] Using cached wallet balance.")
            return self.wallet_balance_cache

        print("[Python Executor] Fetching new wallet balance from exchange...")
        try:
            # Get balance data from exchange - returns list of account balances
            balance_data = self.exchange.get_balance("USDT")
            
            # If balance_data is a list, find the USDT account
            if isinstance(balance_data, list):
                for account in balance_data:
                    if account.get('marginCoin') == 'USDT':
                        equity = account.get('accountEquity')
                        # Update daily loss tracker with starting balance if not already set
                        equity_float = float(equity) if equity else 0.0
                        if self.daily_loss_tracker.start_balance == 0:
                            self.daily_loss_tracker.update_starting_balance(equity_float)
                        # Simpan ke cache
                        self.wallet_balance_cache = equity_float
                        self.balance_last_updated = time.time()
                        return equity_float
                # If no USDT account found in list, return 0
                # Jangan cache jika gagal menemukan USDT
                return 0.0
            # If balance_data is a single account dictionary
            elif isinstance(balance_data, dict):
                equity = balance_data.get('accountEquity')
                # Update daily loss tracker with starting balance if not already set
                equity_float = float(equity) if equity else 0.0
                if self.daily_loss_tracker.start_balance == 0:
                    self.daily_loss_tracker.update_starting_balance(equity_float)
                # Simpan ke cache
                self.wallet_balance_cache = equity_float
                self.balance_last_updated = time.time()
                return equity_float
            else:
                # Jangan cache jika format tidak dikenal
                return 0.0
        except Exception as e:
            print(f"[Python Executor] Error getting wallet balance: {e}")
            # Jangan cache jika gagal
            return None

    def get_active_positions(self) -> Dict:
        """Get all active positions."""
        with self.lock:
            return self.active_positions.copy()

    def update_position_sl_tp(self, symbol: str, new_stop_loss_price: float = None, 
                              new_take_profit_price: float = None) -> Dict:
        """
        Update stop loss and/or take profit for an existing position.
        
        Args:
            symbol (str): Trading symbol
            new_stop_loss_price (float, optional): New stop loss price
            new_take_profit_price (float, optional): New take profit price
        
        Returns:
            Dict: Result of the SL/TP update
        """
        print(f"[Python Executor] Updating SL/TP for position {symbol}, SL: {new_stop_loss_price}, TP: {new_take_profit_price}")
        
        try:
            with self.lock:
                if symbol not in self.active_positions:
                    print(f"[Python Executor] Position {symbol} not found in local tracking")
                    return {"status": "error", "reason": f"Position {symbol} not found"}
                
                position_data = self.active_positions[symbol]
                order_id = position_data.get('main_order_id')
                
                if not order_id:
                    print(f"[Python Executor] Order ID not found for position {symbol}")
                    return {"status": "error", "reason": "Order ID not found for position"}
                
                # Call the exchange to update the SL/TP
                result = self.exchange.modify_order(
                    symbol=symbol,
                    order_id=order_id,
                    new_preset_stop_loss_price=new_stop_loss_price,
                    new_preset_stop_surplus_price=new_take_profit_price
                )
                
                # If successful, update the local position data
                if result and 'orderId' in result:
                    # Update the local tracking data
                    if new_stop_loss_price is not None:
                        self.active_positions[symbol]['stop_loss_price'] = new_stop_loss_price
                    if new_take_profit_price is not None:
                        self.active_positions[symbol]['take_profit_price'] = new_take_profit_price
                        
                    # Persist the changes
                    self._save_persisted_positions()
                    
                    print(f"[Python Executor] SL/TP updated successfully for {symbol}")
                    return {
                        "status": "success",
                        "message": f"SL/TP updated for {symbol}",
                        "new_stop_loss": new_stop_loss_price,
                        "new_take_profit": new_take_profit_price
                    }
                else:
                    print(f"[Python Executor] Failed to update SL/TP for {symbol}, result: {result}")
                    return {"status": "error", "reason": f"Failed to update SL/TP: {result}"}
                    
        except Exception as e:
            print(f"[Python Executor] Error updating SL/TP for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "reason": str(e)}

    def get_position_summary(self) -> Dict:
        """Get summary of all active positions and risk metrics."""
        positions = self.get_active_positions()
        print(f"[Python Executor] Getting position summary - total active positions: {len(positions)}")
        
        total_risk = 0.0
        total_positions = len(positions)
        
        wallet_balance = self._get_wallet_balance()
        print(f"[Python Executor] Wallet balance: {wallet_balance}")
        
        for symbol, pos_data in positions.items():
            # Calculate risk for this position: position_size * entry_price * stop_loss_percent
            risk_amount = abs(pos_data['size'] * pos_data['entry_price'] * self.stop_loss_percent)
            total_risk += risk_amount
            print(f"[Python Executor] Position {symbol} - size: {pos_data['size']}, entry: {pos_data['entry_price']}, risk: {risk_amount}")
            
        risk_percentage = (total_risk / wallet_balance * 100) if wallet_balance and wallet_balance > 0 else 0
        
        summary = {
            "total_positions": total_positions,
            "max_concurrent_positions": self.max_concurrent_positions,
            "total_at_risk": total_risk,
            "wallet_balance": wallet_balance,
            "risk_percentage_of_balance": risk_percentage,
            "risk_per_position_limit": self.risk_percentage
        }
        
        print(f"[Python Executor] Position summary - total_positions: {total_positions}, total_at_risk: {total_risk}, risk_percentage: {risk_percentage}%")
        return summary

    def close_position(self, symbol: str, close_all: bool = True) -> Dict:
        """Manually close a specific position."""
        print(f"[Python Executor] Request to close position for {symbol}, close_all={close_all}")
        try:
            with self.lock:
                if symbol not in self.active_positions:
                    print(f"[Python Executor] Position {symbol} not in local tracking, checking exchange...")
                    # Check if position exists on exchange even if not in our tracking
                    try:
                        exchange_positions = self.exchange.get_positions(symbol)
                        print(f"[Python Executor] Exchange positions for {symbol}: {exchange_positions}")
                        position_exists = any(pos.get('symbol') == symbol and float(pos.get('totalPos', 0)) != 0 for pos in exchange_positions)
                        if not position_exists:
                            print(f"[Python Executor] No active position for {symbol} on exchange or local tracking")
                            return {"status": "error", "reason": f"No active position for {symbol}"}
                        else:
                            print(f"[Python Executor] Position exists on exchange but not in local tracking for {symbol}")
                            # Position exists on exchange but not in our tracking - just close it
                            pass
                    except Exception as e:
                        print(f"[Python Executor] Error checking exchange positions for {symbol}: {e}")
                        return {"status": "error", "reason": f"No active position for {symbol} in local tracking"}
            
            # Get the actual position details from exchange to determine size and side
            try:
                exchange_positions = self.exchange.get_positions(symbol)
                print(f"[Python Executor] Exchange positions data for {symbol}: {exchange_positions}")
                position = next((pos for pos in exchange_positions if pos.get('symbol') == symbol), None)
                if not position:
                    print(f"[Python Executor] No specific position found for {symbol} on exchange")
                    return {"status": "error", "reason": f"No position found for {symbol} on exchange"}
                
                # Determine position size and side
                position_size_str = position.get('totalPos', '0')
                avg_open_price = position.get('avgOpenPrice', 'N/A')
                unrealized_pnl = position.get('unrealizedPnl', 'N/A')
                hold_side = position.get('holdSide', 'N/A').lower()
                
                position_size = abs(float(position_size_str)) if position_size_str else 0.0
                print(f"[Python Executor] Position details from exchange - size: {position_size}, avgOpenPrice: {avg_open_price}, unrealizedPnl: {unrealized_pnl}, holdSide: {hold_side}")
                
                if position_size <= 0:
                    # Position already closed
                    print(f"[Python Executor] Position size is 0 or negative, position already closed for {symbol}")
                    with self.lock:
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                            print(f"[Python Executor] Removed {symbol} from active positions as it was already closed")
                    
                    # Persist the change to file
                    self._save_persisted_positions()
                    
                    return {"status": "success", "message": f"Position {symbol} was already closed"}
                
                # Determine the side to close the position
                # holdSide is typically 'long' or 'short'
                close_side = "buy" if hold_side == "short" else "sell"
                print(f"[Python Executor] Determined close side for {symbol}: {close_side} (hold_side was: {hold_side})")
                
            except Exception as e:
                print(f"[Python Executor] Error getting position details from exchange for {symbol}: {e}")
                # If we can't get exchange position details, use local tracking if available
                with self.lock:
                    if symbol in self.active_positions:
                        position_data = self.active_positions[symbol]
                        position_size = position_data['size']
                        close_side = "sell" if position_data['side'] == "buy" else "buy"
                        print(f"[Python Executor] Using local tracking data - size: {position_size}, close side: {close_side}")
                    else:
                        print(f"[Python Executor] Unable to determine position details for {symbol} from local tracking")
                        return {"status": "error", "reason": f"Unable to determine position details for {symbol}"}
            
            # Place market order to close the position
            print(f"[Python Executor] Placing market order to close position - symbol: {symbol}, side: {close_side}, size: {position_size}")
            order_result = self.exchange.place_order(
                symbol=symbol,
                side=close_side,
                size=position_size,
                order_type="market",
                trade_side=None  # Will be ignored by exchange service for one-way mode
            )
            
            if 'orderId' in order_result:
                order_id = order_result['orderId']
                # Remove from active positions if it exists in our tracking
                with self.lock:
                    if symbol in self.active_positions:
                        del self.active_positions[symbol]
                        print(f"[Python Executor] Successfully closed and removed {symbol} from active positions")
                
                # Persist the change to file
                self._save_persisted_positions()
                
                print(f"[Python Executor] Position {symbol} closed successfully with order ID: {order_id}")
                return {
                    "status": "success", 
                    "message": f"Position {symbol} closed successfully",
                    "order_id": order_id
                }
            else:
                print(f"[Python Executor] Failed to close position via market order for {symbol}, result: {order_result}")
                return {"status": "error", "reason": "Failed to close position via market order"}
                
        except Exception as e:
            print(f"[Python Executor] Error closing position {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "reason": str(e)}

    def execute_trade(self, signal: Dict):
        """Fungsi yang dipanggil dari Rust untuk mengeksekusi trade."""
        print(f"[Python Executor] Menerima sinyal untuk {signal['symbol']}, type: {signal['signal_type']}, price: {signal['price']}, timestamp: {signal['timestamp']}")
        
        # Check circuit breaker
        if self.circuit_breaker_active:
            remaining_time = self.circuit_breaker_reset_time - time.time()
            print(f"[Python Executor] Circuit breaker active: {self.circuit_breaker_reason}. Time until reset: {remaining_time:.2f}s")
            if time.time() >= self.circuit_breaker_reset_time:
                # Reset circuit breaker after timeout
                with self.circuit_breaker_lock:
                    self.circuit_breaker_active = False
                    self.circuit_breaker_reason = ""
                    print("[Python Executor] Circuit breaker reset after timeout")
            else:
                return {"status": "error", "reason": f"Circuit breaker active: {self.circuit_breaker_reason}"}
        
        # Define symbol at the beginning so it's available throughout the function
        symbol = signal['symbol']
        
        # Check for stale signal - verify current price hasn't moved too far from signal price
        signal_price = signal['price']
        try:
            current_price_data = self.exchange.get_ticker(symbol)
            if 'last' in current_price_data:
                current_price = float(current_price_data['last'])
            elif 'lastPr' in current_price_data:
                current_price = float(current_price_data['lastPr'])
            elif isinstance(current_price_data, list) and len(current_price_data) > 0 and 'lastPr' in current_price_data[0]:
                current_price = float(current_price_data[0]['lastPr'])
            else:
                print(f"[Python Executor] Could not get current price for {symbol}")
                current_price = signal_price  # fallback to signal price if can't get current price
        except Exception as e:
            print(f"[Python Executor] Error getting current price for {symbol}: {e}")
            current_price = signal_price  # fallback to signal price if error occurs

        # Make the deviation tolerance configurable
        max_deviation_percent = self.max_price_deviation_percent
        deviation = abs(current_price - signal_price) / signal_price

        if deviation > (max_deviation_percent / 100):
            print(f"[Python Executor] Gagal: Harga telah bergerak terlalu jauh. Sinyal: {signal_price}, Saat Ini: {current_price}")
            return {"status": "error", "reason": "Price deviation too high"}
        
        # Cek Idempotensi
        with self.lock:
            if symbol in self.active_positions:
                print(f"[Python Executor] Gagal: Posisi untuk {symbol} sudah ada. Mengabaikan sinyal duplikat.")
                return {"status": "error", "reason": "Position already exists"}

        if not self._can_open_new_position():
            print(f"[Python Executor] Gagal: Posisi maksimum ({self.max_concurrent_positions}) tercapai. Active positions: {len(self.active_positions)}")
            return {"status": "error", "reason": "Max positions reached"}

        # Check portfolio risk
        try:
            wallet_balance = self._get_wallet_balance()
            active_positions_value = self._calculate_active_positions_value()
            
            is_safe, risk_reason = self.portfolio_risk_tracker.check_portfolio_risk(active_positions_value, wallet_balance)
            if not is_safe:
                print(f"[Python Executor] Gagal: {risk_reason}")
                return {"status": "error", "reason": risk_reason}
                
            # Check daily loss threshold
            daily_loss_pct = self.daily_loss_tracker.get_daily_loss_percentage()
            if daily_loss_pct >= self.daily_loss_limit:
                print(f"[Python Executor] Daily loss threshold exceeded: {daily_loss_pct*100:.2f}% >= {self.daily_loss_limit*100:.2f}%")
                with self.circuit_breaker_lock:
                    self.circuit_breaker_active = True
                    self.circuit_breaker_reason = f"Daily loss threshold exceeded: {daily_loss_pct*100:.2f}%"
                    self.circuit_breaker_reset_time = time.time() + self.max_circuit_breaker_duration
                return {"status": "error", "reason": f"Daily loss threshold exceeded: {daily_loss_pct*100:.2f}%"}
        except Exception as e:
            print(f"[Python Executor] Error checking portfolio risk: {e}")
            return {"status": "error", "reason": f"Portfolio risk check error: {str(e)}"}

        price = signal['price']  # Use the current price instead of signal price if we want to use current price
        signal_type = signal['signal_type'] # Misal "StrongBuy" atau "StrongSell"
        
        side = "buy" if "Buy" in signal_type else "sell"
        
        position_size = self._calculate_position_size(price)
        print(f"[Python Executor] Calculated position size: {position_size} for {symbol} at price {price}")
        
        print(f"[Python Executor] Menempatkan order {side.upper()} untuk {position_size} {symbol} @ {price}")
        
        try:
            # Calculate stop loss price based on signal type
            if "Buy" in signal_type:
                # For long positions, stop loss is below entry price
                stop_loss_price = price * (1 - self.stop_loss_percent)
                print(f"[Python Executor] Long position: stop loss at {stop_loss_price} ({self.stop_loss_percent*100}% below entry)")
            else:
                # For short positions, stop loss is above entry price
                stop_loss_price = price * (1 + self.stop_loss_percent)
                print(f"[Python Executor] Short position: stop loss at {stop_loss_price} ({self.stop_loss_percent*100}% above entry)")
            
            # Calculate take profit price based on signal type with risk-to-reward ratio
            risk_reward_ratio = 1.5  # Default risk-to-reward ratio
            if "Buy" in signal_type:
                take_profit_price = price * (1 + (self.stop_loss_percent * risk_reward_ratio))
                print(f"[Python Executor] Long position: take profit at {take_profit_price} (1:{risk_reward_ratio} risk-reward ratio)")
            else:
                take_profit_price = price * (1 - (self.stop_loss_percent * risk_reward_ratio))
                print(f"[Python Executor] Short position: take profit at {take_profit_price} (1:{risk_reward_ratio} risk-reward ratio)")
            
            # Place the main market order with preset stop loss and take profit
            if self.paper_trading:
                # In paper trading mode, just simulate the order
                order_id = f"SIM_{int(time.time())}_{symbol}"
                order_result = {
                    'orderId': order_id,
                    'symbol': symbol,
                    'side': side,
                    'size': position_size,
                    'price': price,
                    'orderType': 'market',
                    'status': 'filled'
                }
                print(f"[Python Executor] PAPER TRADING: Simulated order placed for {symbol} - {side} {position_size} @ {price}")
            else:
                # Live trading mode
                order_result = self.exchange.place_order(
                    symbol=symbol,
                    side=side,
                    size=position_size,
                    order_type="market",  # Using market for immediate execution
                    preset_stop_loss_price=stop_loss_price,
                    preset_stop_surplus_price=take_profit_price,
                    trade_side=None  # Will be ignored by exchange service for one-way mode
                )
            
            if not order_result or 'orderId' not in order_result:
                print(f"[Python Executor] Failed to place order for {symbol}, result: {order_result}")
                return {"status": "error", "reason": "Order placement failed"}
            
            order_id = order_result['orderId']
            print(f"[Python Executor] Order placed successfully with SL/TP: {order_id} for {symbol}")
            
            # Track the position with entry price, size, stop loss price, take profit price, and order IDs
            position_data = {
                "entry_price": price,
                "size": position_size,
                "side": side,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "main_order_id": order_id,
                "position_id": order_result.get('orderId', ''),  # Using main order ID as position ID
                "timestamp": signal['timestamp']
            }
            
            with self.lock:
                self.active_positions[symbol] = position_data
            
            # Persist the position to file
            self._save_persisted_positions()
            
            print(f"[Python Executor] Position tracked for {symbol}: entry_price={position_data['entry_price']}, size={position_data['size']}, side={position_data['side']}, stop_loss={position_data['stop_loss_price']}, take_profit={position_data['take_profit_price']}")
            print(f"[Python Executor] Total active positions: {len(self.active_positions)} - {list(self.active_positions.keys())}")
            
            # Start a monitoring thread for this position
            monitoring_thread = threading.Thread(
                target=self._monitor_position, 
                args=(symbol,), 
                daemon=True
            )
            monitoring_thread.start()
            print(f"[Python Executor] Started monitoring thread for {symbol}")
            
            return {
                "status": "success", 
                "symbol": symbol, 
                "size": position_size,
                "entry_price": price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "main_order_id": order_id
            }
            
        except Exception as e:
            print(f"[Python Executor] Error executing trade for {symbol}: {e}")
            import traceback
            traceback.print_exc()
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
            print(f"[Monitor] Checking position status for {symbol}, got {len(positions)} positions from exchange")
            
            # Check if the position still exists in the exchange
            for position in positions:
                if position.get('symbol') == symbol:
                    # If position size is 0, it means position is closed
                    position_size_str = position.get('totalPos', '0')
                    avg_open_price = position.get('avgOpenPrice', 'N/A')
                    unrealized_pnl = position.get('unrealizedPnl', 'N/A')
                    
                    if position_size_str is None:
                        position_size_str = '0'
                    position_size = float(position_size_str)
                    
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
                    self.trade_manager._save_persisted_positions()
                    
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


# Buat instance global agar bisa diakses dari Rust
trade_manager = TradeManager()


def handle_trade_signal(signal: Dict):
    """Wrapper fungsi sederhana untuk dipanggil dari Rust."""
    return trade_manager.execute_trade(signal)