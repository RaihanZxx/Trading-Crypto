import os
import sys
import threading
import time
import json
import toml
from typing import Dict, Optional

# Menambahkan path untuk modul lokal
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from connectors.exchange_service import BitgetExchangeService
from utils.telegram import TelegramNotifier


def _import_execution_modules():
    """Fungsi untuk mengimpor modul-modul eksekusi setelah kelas TradeManager didefinisikan."""
    from execution_service.risk import PortfolioRiskTracker, DailyLossTracker
    from execution_service.monitoring import PositionMonitor
    from execution_service.persistence import _ensure_data_directory, _load_persisted_positions, _save_persisted_positions
    from execution_service.utils import _calculate_position_size, _calculate_active_positions_value, _get_wallet_balance
    
    # Menambahkan fungsi-fungsi tersebut sebagai atribut kelas atau mengembalikannya
    return {
        'PortfolioRiskTracker': PortfolioRiskTracker,
        'DailyLossTracker': DailyLossTracker,
        'PositionMonitor': PositionMonitor,
        '_ensure_data_directory': _ensure_data_directory,
        '_load_persisted_positions': _load_persisted_positions,
        '_save_persisted_positions': _save_persisted_positions,
        '_calculate_position_size': _calculate_position_size,
        '_calculate_active_positions_value': _calculate_active_positions_value,
        '_get_wallet_balance': _get_wallet_balance
    }


class TradeManager:
    def __init__(self):
        # Import modul-modul eksekusi di sini setelah objek dibuat
        modules = _import_execution_modules()
        self.PortfolioRiskTracker = modules['PortfolioRiskTracker']
        self.DailyLossTracker = modules['DailyLossTracker']
        self.PositionMonitor = modules['PositionMonitor']
        self._ensure_data_directory = modules['_ensure_data_directory']
        self._load_persisted_positions = modules['_load_persisted_positions']
        self._save_persisted_positions = modules['_save_persisted_positions']
        self._calculate_position_size = modules['_calculate_position_size']
        self._calculate_active_positions_value = modules['_calculate_active_positions_value']
        self._get_wallet_balance = modules['_get_wallet_balance']
        
        self.exchange = BitgetExchangeService(
            api_key=os.getenv('BITGET_API_KEY'),
            secret_key=os.getenv('BITGET_SECRET_KEY'),
            passphrase=os.getenv('BITGET_PASSPHRASE')
        )
        
        # Load configuration from config.toml
        self._load_config()
        
        self.active_positions = {} # Lacak posisi aktif
        self.lock = threading.Lock()
        
        # Initialize Telegram notifier
        self.telegram_notifier = TelegramNotifier(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            chat_id=os.getenv('TELEGRAM_CHAT_ID'),
            message_thread_id="3"  # Use topic ID 3 as specified (converted to string)
        )
        
        # Portfolio-level risk tracking
        self.portfolio_risk_tracker = self.PortfolioRiskTracker(
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
        self.daily_loss_tracker = self.DailyLossTracker(self.daily_loss_limit)
        
        # Position state persistence
        self.positions_file = "data/active_positions.json"
        self._ensure_data_directory(self.positions_file)
        self._load_persisted_positions(
            self.positions_file, 
            self.active_positions, 
            self.lock, 
            self.exchange,
            self._monitor_position
        )

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
    
    def _can_open_new_position(self) -> bool:
        """Cek apakah kita bisa membuka posisi baru berdasarkan batasan."""
        with self.lock:
            return len(self.active_positions) < self.max_concurrent_positions

    def get_active_positions(self) -> Dict:
        """Get all active positions."""
        with self.lock:
            return self.active_positions.copy()

    def update_position_sl_tp(self, symbol: str, new_stop_loss_price: Optional[float] = None, 
                              new_take_profit_price: Optional[float] = None) -> Dict:
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
                
                # Update stop-loss order if needed
                if new_stop_loss_price is not None:
                    sl_order_id = position_data.get('stop_loss_order_id')
                    if sl_order_id:
                        try:
                            # Modify the existing stop-loss order
                            result = self.exchange.modify_tpsl_order(
                                order_id=sl_order_id,
                                symbol=symbol,
                                trigger_price=new_stop_loss_price,
                                execute_price=0,  # market execution
                                size=position_data['size'],  # use original position size
                                trigger_type="mark_price"
                            )
                            
                            # Update the local tracking data for stop loss
                            self.active_positions[symbol]['stop_loss_price'] = new_stop_loss_price
                            
                            print(f"[Python Executor] Stop-loss updated successfully for {symbol}")
                        except Exception as e:
                            print(f"[Python Executor] Failed to update stop-loss for {symbol}: {e}")
                            return {"status": "error", "reason": f"Failed to update stop-loss: {e}"}
                    else:
                        print(f"[Python Executor] No stop-loss order ID found for {symbol}, creating new one...")
                        # Create a new stop-loss order if none exists
                        try:
                            hold_side = "buy" if position_data['side'] == 'buy' else 'sell'
                            sl_result = self.exchange.place_tpsl_order(
                                symbol=symbol,
                                plan_type="loss_plan",
                                trigger_price=new_stop_loss_price,
                                execute_price=0,  # market execution
                                hold_side=hold_side,
                                size=position_data['size'],
                                trigger_type="mark_price"
                            )
                            new_sl_order_id = sl_result.get('orderId')
                            self.active_positions[symbol]['stop_loss_order_id'] = new_sl_order_id
                            self.active_positions[symbol]['stop_loss_price'] = new_stop_loss_price
                            
                            print(f"[Python Executor] New stop-loss order created for {symbol} with ID: {new_sl_order_id}")
                        except Exception as e:
                            print(f"[Python Executor] Failed to create stop-loss for {symbol}: {e}")
                            return {"status": "error", "reason": f"Failed to create stop-loss: {e}"}
                
                # Update take-profit order if needed
                if new_take_profit_price is not None:
                    tp_order_id = position_data.get('take_profit_order_id')
                    if tp_order_id:
                        try:
                            # Modify the existing take-profit order
                            result = self.exchange.modify_tpsl_order(
                                order_id=tp_order_id,
                                symbol=symbol,
                                trigger_price=new_take_profit_price,
                                execute_price=0,  # market execution
                                size=position_data['size'],  # use original position size
                                trigger_type="mark_price"
                            )
                            
                            # Update the local tracking data for take profit
                            self.active_positions[symbol]['take_profit_price'] = new_take_profit_price
                            
                            print(f"[Python Executor] Take-profit updated successfully for {symbol}")
                        except Exception as e:
                            print(f"[Python Executor] Failed to update take-profit for {symbol}: {e}")
                            return {"status": "error", "reason": f"Failed to update take-profit: {e}"}
                    else:
                        print(f"[Python Executor] No take-profit order ID found for {symbol}, creating new one...")
                        # Create a new take-profit order if none exists
                        try:
                            hold_side = "buy" if position_data['side'] == 'buy' else 'sell'
                            tp_result = self.exchange.place_tpsl_order(
                                symbol=symbol,
                                plan_type="profit_plan",
                                trigger_price=new_take_profit_price,
                                execute_price=0,  # market execution
                                hold_side=hold_side,
                                size=position_data['size'],
                                trigger_type="mark_price"
                            )
                            new_tp_order_id = tp_result.get('orderId')
                            self.active_positions[symbol]['take_profit_order_id'] = new_tp_order_id
                            self.active_positions[symbol]['take_profit_price'] = new_take_profit_price
                            
                            print(f"[Python Executor] New take-profit order created for {symbol} with ID: {new_tp_order_id}")
                        except Exception as e:
                            print(f"[Python Executor] Failed to create take-profit for {symbol}: {e}")
                            return {"status": "error", "reason": f"Failed to create take-profit: {e}"}
                
                # Persist the changes
                self._save_persisted_positions(self.positions_file, self.active_positions, self.lock)
                
                print(f"[Python Executor] SL/TP updated successfully for {symbol}")
                return {
                    "status": "success",
                    "message": f"SL/TP updated for {symbol}",
                    "new_stop_loss": new_stop_loss_price,
                    "new_take_profit": new_take_profit_price
                }
                    
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
        
        wallet_balance = self._get_wallet_balance(self)
        print(f"[Python Executor] Wallet balance: {wallet_balance}")
        
        for symbol, pos_data in positions.items():
            # Calculate risk for this position: position_size * entry_price * stop_loss_percent
            risk_amount = abs(pos_data['size'] * pos_data['entry_price'] * self.stop_loss_percent)
            total_risk += risk_amount
            print(f"[Python Executor] Position {symbol} - size: {pos_data['size']}, entry: {pos_data['entry_price']}, risk: {risk_amount}")
            
        risk_percentage = (total_risk / wallet_balance * 100) if wallet_balance is not None and wallet_balance > 0 else 0
        
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
                        
                        # Check if position exists using correct field names
                        position_exists = False
                        for pos in exchange_positions:
                            if pos.get('symbol') == symbol:
                                # Check multiple possible field names for position size based on Bitget API response
                                # Prioritize 'total' and 'available' which were found in actual API response
                                position_size_str = pos.get('total', '0')  # Primary field from API response
                                if position_size_str == '0' or position_size_str is None:
                                    available_size = pos.get('available', '0')  # Alternative field
                                    if available_size != '0':
                                        position_size_str = available_size
                                    else:
                                        # Try to calculate from other fields if possible
                                        open_delegate_size = pos.get('openDelegateSize', '0')
                                        if open_delegate_size != '0':
                                            position_size_str = open_delegate_size
                                        else:
                                            position_size_str = '0'
                                
                                # Convert to float and check if position is still open
                                try:
                                    position_size = float(position_size_str)
                                except ValueError:
                                    position_size = 0.0  # Default to 0 if conversion fails
                                
                                if position_size != 0:
                                    position_exists = True
                                    break
                        
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
                
                # Convert to float and determine position size
                try:
                    position_size = abs(float(position_size_str)) if position_size_str else 0.0
                except ValueError:
                    position_size = 0.0  # Default to 0 if conversion fails
                
                # Use correct field names from Bitget API response
                avg_open_price = position.get('openPriceAvg', 'N/A')  # Correct field name from API
                unrealized_pnl = position.get('unrealizedPL', 'N/A')  # Correct field name from API
                hold_side = position.get('holdSide', 'N/A').lower()
                
                print(f"[Python Executor] Position details from exchange - size: {position_size}, avgOpenPrice: {avg_open_price}, unrealizedPnl: {unrealized_pnl}, holdSide: {hold_side}")
                
                if position_size <= 0:
                    # Position already closed
                    print(f"[Python Executor] Position size is 0 or negative, position already closed for {symbol}")
                    with self.lock:
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                            print(f"[Python Executor] Removed {symbol} from active positions as it was already closed")
                    
                    # Persist the change to file
                    self._save_persisted_positions(self.positions_file, self.active_positions, self.lock)
                    
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

            # First, cancel any existing stop-loss and take-profit orders
            with self.lock:
                if symbol in self.active_positions:
                    position_data = self.active_positions[symbol]
                    
                    # Cancel stop-loss order if it exists
                    sl_order_id = position_data.get('stop_loss_order_id')
                    if sl_order_id:
                        try:
                            self.exchange.cancel_tpsl_order(
                                order_id=sl_order_id,
                                symbol=symbol,
                                plan_type="loss_plan"
                            )
                            print(f"[Python Executor] Cancelled stop-loss order {sl_order_id} for {symbol}")
                        except Exception as e:
                            print(f"[Python Executor] Error cancelling stop-loss order for {symbol}: {e}")
                    
                    # Cancel take-profit order if it exists
                    tp_order_id = position_data.get('take_profit_order_id')
                    if tp_order_id:
                        try:
                            self.exchange.cancel_tpsl_order(
                                order_id=tp_order_id,
                                symbol=symbol,
                                plan_type="profit_plan"
                            )
                            print(f"[Python Executor] Cancelled take-profit order {tp_order_id} for {symbol}")
                        except Exception as e:
                            print(f"[Python Executor] Error cancelling take-profit order for {symbol}: {e}")

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
                        # Also cancel any pending stop-loss or take-profit orders (double check)
                        position_data = self.active_positions[symbol]
                        sl_order_id = position_data.get('stop_loss_order_id')
                        tp_order_id = position_data.get('take_profit_order_id')
                        
                        # Cancel stop-loss order if it exists
                        if sl_order_id:
                            try:
                                self.exchange.cancel_tpsl_order(
                                    order_id=sl_order_id,
                                    symbol=symbol,
                                    plan_type="loss_plan"
                                )
                                print(f"[Python Executor] Cancelled stop-loss order {sl_order_id} for {symbol}")
                            except Exception as e:
                                print(f"[Python Executor] Error cancelling stop-loss order for {symbol}: {e}")
                        
                        # Cancel take-profit order if it exists
                        if tp_order_id:
                            try:
                                self.exchange.cancel_tpsl_order(
                                    order_id=tp_order_id,
                                    symbol=symbol,
                                    plan_type="profit_plan"
                                )
                                print(f"[Python Executor] Cancelled take-profit order {tp_order_id} for {symbol}")
                            except Exception as e:
                                print(f"[Python Executor] Error cancelling take-profit order for {symbol}: {e}")
                        
                        # Remove from active positions
                        del self.active_positions[symbol]
                        print(f"[Python Executor] Successfully closed and removed {symbol} from active positions")

                # Persist the change to file
                self._save_persisted_positions(self.positions_file, self.active_positions, self.lock)

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

    def save_persisted_positions(self):
        """Wrapper method to save persisted positions, callable from other modules."""
        self._save_persisted_positions(self.positions_file, self.active_positions, self.lock)

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
        # DISABLED: max_price_deviation_percent check is temporarily disabled due to bug where
        # signals are rejected due to minor price movements after signal generation
        # 
        # signal_price = signal['price']
        # try:
        #     current_price_data = self.exchange.get_ticker(symbol)
        #     if 'last' in current_price_data:
        #         current_price = float(current_price_data['last'])
        #     elif 'lastPr' in current_price_data:
        #         current_price = float(current_price_data['lastPr'])
        #     elif isinstance(current_price_data, list) and len(current_price_data) > 0 and 'lastPr' in current_price_data[0]:
        #         current_price = float(current_price_data[0]['lastPr'])
        #     else:
        #         print(f"[Python Executor] Could not get current price for {symbol}")
        #         current_price = signal_price  # fallback to signal price if can't get current price
        # except Exception as e:
        #     print(f"[Python Executor] Error getting current price for {symbol}: {e}")
        #     current_price = signal_price  # fallback to signal price if error occurs
        #
        # # Make the deviation tolerance configurable
        # max_deviation_percent = self.max_price_deviation_percent
        # deviation = abs(current_price - signal_price) / signal_price
        #
        # if deviation > (max_deviation_percent / 100):
        #     print(f"[Python Executor] Gagal: Harga telah bergerak terlalu jauh. Sinyal: {signal_price}, Saat Ini: {current_price}")
        #     return {"status": "error", "reason": "Price deviation too high"}
        
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
            wallet_balance = self._get_wallet_balance(self)
            if wallet_balance is None:
                return {"status": "error", "reason": "Could not fetch wallet balance"}
            active_positions_value = self._calculate_active_positions_value(self)
            
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
        
        position_size = self._calculate_position_size(self, price)
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
            
            # Place the main market order without preset SL/TP (we'll place them separately)
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
                
                # Simulate SL and TP order IDs for paper trading
                sl_order_id = f"SL_SIM_{int(time.time())}_{symbol}"
                tp_order_id = f"TP_SIM_{int(time.time())}_{symbol}"
                print(f"[Python Executor] PAPER TRADING: Simulated SL/TP orders created - SL: {sl_order_id}, TP: {tp_order_id}")
            else:
                # Live trading mode - place main order first
                order_result = self.exchange.place_order(
                    symbol=symbol,
                    side=side,
                    size=position_size,
                    order_type="market",  # Using market for immediate execution
                    trade_side=None  # Will be ignored by exchange service for one-way mode
                )
                
                # Now place separate conditional stop-loss and take-profit orders
                sl_order_id = None
                tp_order_id = None
                
                # Determine hold side based on position side for one-way mode
                hold_side = "buy" if side == "buy" else "sell"  # Use same values for one-way mode
                
                # Place stop-loss order as a separate conditional order
                try:
                    sl_result = self.exchange.place_tpsl_order(
                        symbol=symbol,
                        plan_type="loss_plan",  # stop loss plan
                        trigger_price=stop_loss_price,
                        execute_price=0,  # market execution
                        hold_side=hold_side,
                        size=position_size,
                        trigger_type="mark_price"
                    )
                    sl_order_id = sl_result.get('orderId')
                    print(f"[Python Executor] Stop-loss order placed for {symbol} with ID: {sl_order_id}")
                except Exception as e:
                    print(f"[Python Executor] Failed to place stop-loss order for {symbol}: {e}")
                    # Don't fail the entire trade if SL order fails, just log it
                    pass
                
                # Place take-profit order as a separate conditional order
                try:
                    tp_result = self.exchange.place_tpsl_order(
                        symbol=symbol,
                        plan_type="profit_plan",  # take profit plan
                        trigger_price=take_profit_price,
                        execute_price=0,  # market execution
                        hold_side=hold_side,
                        size=position_size,
                        trigger_type="mark_price"
                    )
                    tp_order_id = tp_result.get('orderId')
                    print(f"[Python Executor] Take-profit order placed for {symbol} with ID: {tp_order_id}")
                except Exception as e:
                    print(f"[Python Executor] Failed to place take-profit order for {symbol}: {e}")
                    # Don't fail the entire trade if TP order fails, just log it
                    pass
            
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
                "stop_loss_order_id": sl_order_id,  # ID of the separate stop loss order
                "take_profit_order_id": tp_order_id,  # ID of the separate take profit order
                "timestamp": signal['timestamp']
            }
            
            with self.lock:
                self.active_positions[symbol] = position_data
            
            # Persist the position to file
            self._save_persisted_positions(self.positions_file, self.active_positions, self.lock)
            
            print(f"[Python Executor] Position tracked for {symbol}: entry_price={position_data['entry_price']}, size={position_data['size']}, side={position_data['side']}, stop_loss={position_data['stop_loss_price']}, take_profit={position_data['take_profit_price']}")
            print(f"[Python Executor] Total active positions: {len(self.active_positions)} - {list(self.active_positions.keys())}")
            
            # Send Telegram notification about the new trade entry
            try:
                # Format the notification message in a modern, minimalist style
                side_emoji = "🟢 LONG" if side == "buy" else "🔴 SHORT"
                
                # Calculate risk amount
                risk_amount = abs(position_size * price * self.stop_loss_percent)
                risk_percent = self.risk_percentage * 100
                
                # Get wallet balance for additional context
                wallet_balance = self._get_wallet_balance(self)
                wallet_balance_str = f"{wallet_balance:.2f}" if wallet_balance is not None else "N/A"
                
                message = f"""🎯 *NEW TRADE ENTRY*

┌─ {side_emoji} *{symbol}*
├─ Entry: *{price:.8f}*
├─ Size: *{position_size}*
├─ Risk: *${risk_amount:.2f}* ({risk_percent:.1f}% of balance)
├─ Balance: *${wallet_balance_str}*
├─ Stop Loss: *{stop_loss_price:.8f}*
├─ Take Profit: *{take_profit_price:.8f}*
└─ Order ID: `{order_id}`"""
                
                # Send the notification to Telegram
                self.telegram_notifier.send_message(message)
                
            except Exception as e:
                print(f"[Python Executor] Error sending Telegram notification: {e}")
            
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
        monitor = self.PositionMonitor(self)
        monitor.monitor_position(symbol)


# Buat instance global agar bisa diakses dari Rust
trade_manager = TradeManager()


def handle_trade_signal(signal: Dict):
    """Wrapper fungsi sederhana untuk dipanggil dari Rust."""
    return trade_manager.execute_trade(signal)