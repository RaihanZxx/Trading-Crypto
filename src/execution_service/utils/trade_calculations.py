import time
from typing import Optional


def _calculate_position_size(trade_manager, price: float) -> float:
    """Hitung ukuran posisi dalam satuan koin."""
    with trade_manager.lock:  # Tambahkan lock di sini
        # Dynamic risk: percentage of total wallet balance
        wallet_balance = _get_wallet_balance(trade_manager)  # _get_wallet_balance tidak perlu lock jika dipanggil dari sini
        if wallet_balance is not None and wallet_balance > 0:
            # Calculate max risk amount (1% of balance)
            risk_amount = wallet_balance * trade_manager.risk_percentage
        else:
            raise ValueError("Could not fetch wallet balance or balance is zero")
        
        # Calculate position size in contracts to ensure risk = risk_amount
        # Risk = Position_Size * Price * Stop_Loss_Percentage
        # Position_Size = Risk / (Price * Stop_Loss_Percentage)
        position_size = risk_amount / (price * trade_manager.stop_loss_percent)
        
        # Ensure minimum size based on exchange requirements
        # Use a more reasonable minimum based on typical exchange requirements
        # For most exchange pairs, this will be around 0.001 to 0.1 contracts
        minimum_size = 0.01  # More realistic minimum for typical trading pairs
        position_size = max(position_size, minimum_size)
        
        # For very low-value coins like MYX, we might need to adjust further
        # If price is very low (indicating a small coin), adjust minimum accordingly
        if price < 0.01:  # For low-cost coins like MYXUSDT
            minimum_size = 1.0  # Minimum of 1 contract for low-value coins
            position_size = max(position_size, minimum_size)
        
        return round(position_size, 4)  # Bulatkan ke 4 desimal for better precision


def _calculate_active_positions_value(trade_manager) -> float:
    """Calculate the total value of all active positions."""
    total_value = 0.0
    with trade_manager.lock:
        for symbol, position_data in trade_manager.active_positions.items():
            try:
                # Get current price for the symbol
                current_price_data = trade_manager.exchange.get_ticker(symbol)
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


def _get_wallet_balance(trade_manager) -> Optional[float]:
    """Get the current wallet balance."""
    now = time.time()
    # Gunakan cache jika masih valid
    if (trade_manager.wallet_balance_cache is not None and 
        (now - trade_manager.balance_last_updated) < trade_manager.BALANCE_CACHE_DURATION):
        print("[Python Executor] Using cached wallet balance.")
        return trade_manager.wallet_balance_cache

    print("[Python Executor] Fetching new wallet balance from exchange...")
    try:
        # Get balance data from exchange - returns list of account balances
        balance_data = trade_manager.exchange.get_balance("USDT")
        
        # If balance_data is a list, find the USDT account
        if isinstance(balance_data, list):
            for account in balance_data:
                if account.get('marginCoin') == 'USDT':
                    equity = account.get('accountEquity')
                    # Update daily loss tracker with starting balance if not already set
                    equity_float = float(equity) if equity else 0.0
                    if trade_manager.daily_loss_tracker.start_balance == 0:
                        trade_manager.daily_loss_tracker.update_starting_balance(equity_float)
                    # Simpan ke cache
                    trade_manager.wallet_balance_cache = equity_float
                    trade_manager.balance_last_updated = time.time()
                    return equity_float
            # If no USDT account found in list, return 0
            # Jangan cache jika gagal menemukan USDT
            return 0.0
        # If balance_data is a single account dictionary
        elif isinstance(balance_data, dict):
            equity = balance_data.get('accountEquity')
            # Update daily loss tracker with starting balance if not already set
            equity_float = float(equity) if equity else 0.0
            if trade_manager.daily_loss_tracker.start_balance == 0:
                trade_manager.daily_loss_tracker.update_starting_balance(equity_float)
            # Simpan ke cache
            trade_manager.wallet_balance_cache = equity_float
            trade_manager.balance_last_updated = time.time()
            return equity_float
        else:
            # Jangan cache jika format tidak dikenal
            return 0.0
    except Exception as e:
        print(f"[Python Executor] Error getting wallet balance: {e}")
        # Jangan cache jika gagal
        return None