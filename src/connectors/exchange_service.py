import os
import hashlib
import hmac
import json
import time
import requests
import base64
from typing import Dict, Optional, Any, Union, List
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class BitgetExchangeService:
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, passphrase: Optional[str] = None):
        """Initialize Bitget exchange service with API credentials."""
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.passphrase = passphrase or ""
        self.base_url = "https://api.bitget.com"
        
        # Create a session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)
    
    def _sign_request(self, timestamp: int, method: str, request_path: str, 
                     query_string: str = "", body: str = "") -> str:
        """Sign request using HMAC SHA256."""
        if query_string:
            message = str(timestamp) + method.upper() + request_path + "?" + query_string + body
        else:
            message = str(timestamp) + method.upper() + request_path + body
            
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(signature.digest()).decode('utf-8')
    
    def _exponential_backoff_retry(self, func, max_retries=3, base_delay=1):
        """Retry a function with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return func()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # Jika ini adalah percobaan terakhir, lempar error
                if attempt == max_retries - 1:
                    raise e
                
                # Hitung delay dengan exponential backoff + jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Koneksi error: {e}. Mencoba lagi dalam {delay:.2f} detik... (percobaan {attempt + 1}/{max_retries})")
                time.sleep(delay)
            except Exception as e:
                # Untuk error lain, tidak perlu retry
                raise e

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Bitget API."""
        timestamp = self._get_timestamp()
        
        # Prepare query string and body
        query_string = urlencode(params) if params else ""
        body = json.dumps(data) if data else ""
        
        # Sign the request
        signature = self._sign_request(timestamp, method, endpoint, query_string, body)
        
        # Prepare headers and URL
        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': str(timestamp),
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        if query_string:
            url += f"?{query_string}"
            
        # Prepare request function for retry
        def _request():
            response = self.session.get(url, headers=headers, timeout=30) if method.upper() == 'GET' else \
                       self.session.post(url, headers=headers, data=body, timeout=30)
            
            try:
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError:
                print(f"HTTP Error occurred: {response.status_code}")
                print(f"Response text: {response.text}")
                try:
                    return response.json()
                except:
                    return {"code": str(response.status_code), "message": response.text}
        
        # Execute request with retry and error handling
        try:
            result = self._exponential_backoff_retry(_request)
            return result if isinstance(result, dict) else {"code": "unknown_error", "message": "Invalid response format"}
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error occurred: {e}")
            return {"code": "connection_error", "message": str(e)}
        except requests.exceptions.Timeout as e:
            print(f"Request timeout occurred: {e}")
            return {"code": "timeout_error", "message": str(e)}
        except requests.exceptions.RequestException as e:
            print(f"Request error occurred: {e}")
            return {"code": "request_error", "message": str(e)}
        except Exception as e:
            print(f"Unexpected error occurred: {e}")
            return {"code": "unknown_error", "message": str(e)}
    
    def get_futures_symbols(self) -> List[Dict]:
        """Get all futures symbols."""
        endpoint = "/api/v2/mix/market/contracts"
        params = {"productType": "USDT-FUTURES"}
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get futures symbols due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get futures symbols: {response}")
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Get specific symbol information including precision details."""
        endpoint = "/api/v2/mix/market/contracts"
        params = {"productType": "USDT-FUTURES"}
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get symbol info due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            symbols_data = response.get('data', [])
            # Find the specific symbol
            for sym_data in symbols_data:
                if sym_data.get('symbol') == symbol:
                    return sym_data
            # If specific symbol not found, return empty dict
            return {}
        else:
            raise Exception(f"Failed to get symbol info: {response}")

    def _get_precision_for_symbol(self, symbol: str) -> Dict[str, Union[int, float]]:
        """Get price and size precision for a specific symbol."""
        try:
            symbol_info = self.get_symbol_info(symbol)
            if symbol_info:
                # Extract precision from symbol info - these field names are based on typical exchange APIs
                price_place = symbol_info.get('pricePlace', 4)  # Default to 4 decimal places
                volume_place = symbol_info.get('volumePlace', 4)  # Default to 4 decimal places
                # Extract min and max order sizes, and step size
                min_size = symbol_info.get('minTradeAmount', 0)  # Minimum order size
                max_size = symbol_info.get('maxTradeAmount', float('inf'))  # Maximum order size
                step_size = symbol_info.get('quotePrecision', 1)  # Step size (this field might vary)
                
                return {
                    'price_precision': int(price_place) if price_place else 4,
                    'size_precision': int(volume_place) if volume_place else 4,
                    'min_size': float(min_size) if min_size else 0,
                    'max_size': float(max_size) if max_size else float('inf'),
                    'step_size': float(step_size) if step_size else 1  # Default step size is 1
                }
        except Exception:
            # If we can't fetch precision, use defaults
            pass
        
        # Default precision for different types of symbols
        if 'SATS' in symbol:
            # For SATS and other very low-value coins, use higher precision
            return {
                'price_precision': 8, 
                'size_precision': 4,
                'min_size': 0,
                'max_size': float('inf'),
                'step_size': 1
            }
        elif 'BTC' in symbol:
            return {
                'price_precision': 6, 
                'size_precision': 4,
                'min_size': 0,
                'max_size': float('inf'),
                'step_size': 1
            }
        elif 'ETH' in symbol:
            return {
                'price_precision': 5, 
                'size_precision': 4,
                'min_size': 0,
                'max_size': float('inf'),
                'step_size': 1
            }
        else:
            # Default for other symbols
            return {
                'price_precision': 4, 
                'size_precision': 4,
                'min_size': 0,
                'max_size': float('inf'),
                'step_size': 1
            }
    
    def _validate_and_round_size(self, symbol: str, size: float) -> float:
        """Validate and round the order size according to symbol's rules."""
        try:
            precision_info = self._get_precision_for_symbol(symbol)
            
            # Check minimum size
            min_size = precision_info.get('min_size', 0)
            if size < min_size:
                raise ValueError(f"Order size {size} is below minimum size {min_size} for {symbol}")
            
            # Check maximum size
            max_size = precision_info.get('max_size', float('inf'))
            if size > max_size:
                raise ValueError(f"Order size {size} exceeds maximum size {max_size} for {symbol}")
            
            # Round to step size
            step_size = precision_info.get('step_size', 1)
            size_precision = precision_info.get('size_precision', 4)
            
            # Calculate the valid size based on step size
            # (size // step_size) * step_size ensures the size is a multiple of step_size
            import math
            valid_size = math.floor(size / step_size) * step_size
            
            # Format to appropriate precision
            valid_size = round(valid_size, int(size_precision))
            
            return valid_size
            
        except Exception as e:
            print(f"Error validating and rounding size for {symbol}: {e}")
            # As fallback, return the original size if we can't validate it
            return size
    
    def get_ticker(self, symbol: str) -> Dict:
        """Get ticker for a specific symbol."""
        endpoint = "/api/v2/mix/market/ticker"
        params = {"symbol": symbol, "productType": "USDT-FUTURES"}
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get ticker for {symbol} due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to get ticker for {symbol}: {response}")
    
    def get_all_tickers(self) -> List[Dict]:
        """Get tickers for all symbols."""
        endpoint = "/api/v2/mix/market/tickers"
        params = {"productType": "USDT-FUTURES"}
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get all tickers due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get all tickers: {response}")
    
    def get_candlesticks(self, symbol: str, limit: int = 1, granularity: str = "1H", start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[Dict]:
        """Get candlesticks for a symbol."""
        endpoint = "/api/v2/mix/market/candles"
        params = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "granularity": granularity,
            "limit": limit
        }
        
        # Add time range parameters if provided
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
            
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get candlesticks for {symbol} due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get candlesticks for {symbol}: {response}")
    
    def get_open_price_at_7am_wib(self, symbol: str, date: str) -> Optional[float]:
        """
        Get open price at 7:00 AM WIB (00:00 UTC) for a symbol on specific date.
        Uses the openUtc field from the ticker data which represents the daily open price.
        """
        try:
            # Get ticker data for the symbol
            ticker_data = self.get_ticker(symbol)
            
            # Check if ticker data contains the openUtc field
            if ticker_data and isinstance(ticker_data, list) and len(ticker_data) > 0:
                # The ticker data is returned as a list with one element
                ticker = ticker_data[0]
                if 'openUtc' in ticker and ticker['openUtc']:
                    return float(ticker['openUtc'])
            
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error getting open price for {symbol}: {e}")
            return None
        except requests.exceptions.Timeout as e:
            print(f"Timeout error getting open price for {symbol}: {e}")
            return None
        except Exception as e:
            print(f"Error getting open price for {symbol}: {e}")
            return None

    def get_balance(self, margin_coin: str = "USDT") -> Dict:
        """
        Get account balance for futures trading.
        
        Args:
            margin_coin (str): The margin coin to get balance for (default: USDT)
        
        Returns:
            Dict: Account balance information
        """
        endpoint = "/api/v2/mix/account/accounts"
        params = {
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin
        }
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get balance due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to get balance: {response}")
    
    def place_order(self, symbol: str, side: str, size: float, order_type: str = "limit", 
                   price: Optional[float] = None, time_in_force: str = "normal", 
                   client_oid: Optional[str] = None, margin_mode: str = "crossed", 
                   reduce_only: str = "NO", preset_stop_loss_price: Optional[float] = None,
                   preset_stop_surplus_price: Optional[float] = None,
                   preset_stop_loss_execute_price: Optional[float] = None,
                   preset_stop_surplus_execute_price: Optional[float] = None,
                   trade_side: Optional[str] = None) -> Dict:
        """
        Place an order on Bitget.
        
        Args:
            symbol (str): Trading symbol (e.g., "BTCUSDT")
            side (str): "buy" or "sell"
            size (float): Order size in contracts
            order_type (str): "limit", "market", "post_only", etc.
            price (float, optional): Price for limit orders
            time_in_force (str): "normal", "post_only", "gtc", etc.
            client_oid (str, optional): Client order ID
            margin_mode (str): "crossed" or "isolated"
            reduce_only (str): "YES" or "NO"
            preset_stop_loss_price (float, optional): Stop loss price
            preset_stop_surplus_price (float, optional): Take profit price
            preset_stop_loss_execute_price (float, optional): Stop loss execution price
            preset_stop_surplus_execute_price (float, optional): Take profit execution price
            trade_side (str, optional): "open" or "close" - required for hedge mode (omit for one-way mode)
        
        Returns:
            Dict: Order response
        """
        endpoint = "/api/v2/mix/order/place-order"
        
        # Validate required parameters
        if side.lower() not in ["buy", "sell"]:
            raise ValueError(f"Side must be 'buy' or 'sell', got: {side}")
        
        if order_type.lower() not in ["limit", "market"]:
            raise ValueError(f"Order type must be 'limit' or 'market', got: {order_type}")
        
        # Validate and round the size according to symbol's rules
        validated_size = self._validate_and_round_size(symbol, size)
        
        # Determine margin coin from symbol (usually USDT for USDT-FUTURES)
        margin_coin = "USDT"  # Default for USDT-FUTURES
        if "USDC" in symbol:
            margin_coin = "USDC"
            
        # Prepare order data based on Bitget API v2 requirements
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",  # This should match Bitget's requirements
            "marginMode": margin_mode,  # "crossed" or "isolated"
            "marginCoin": margin_coin,  # Required field
            "side": side.lower(),
            "orderType": order_type.lower(),  # "limit", "market", etc.
            "size": str(validated_size),  # Convert validated size to string as required by API
            "reduceOnly": reduce_only  # "YES" or "NO"
        }
        
        # Add tradeSide parameter only for hedge mode (omit for one-way mode)
        # According to API docs: "Ignore the tradeSide parameter when position mode is in one-way-mode"
        if trade_side is not None and trade_side.lower() in ["open", "close"]:
            data["tradeSide"] = trade_side.lower()
        
        # Add time in force for limit orders (only for limit orders)
        if order_type.lower() == "limit":
            # Map time_in_force to force parameter
            if time_in_force.lower() in ["post_only"]:
                data["force"] = "post_only"
            elif time_in_force.lower() in ["ioc", "fok", "gtc"]:
                data["force"] = time_in_force.lower()
            else:
                data["force"] = "gtc"  # default
            
            if price is None:
                raise ValueError("Price is required for limit orders")
            
            # Format price according to contract requirements
            # Use dynamic precision based on the symbol instead of fixed 4 decimal places
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_price = round(price, int(price_precision))
            data["price"] = str(formatted_price)
        else:
            # For market orders, ensure no force parameter is set (as it's only for limit orders)
            # According to API docs: "Required if the orderType is limit"
            if price is not None:
                # For market orders, price should not be included
                print(f"Warning: Price specified for market order, will be ignored")
        
        # Add preset stop loss and take profit prices if provided
        if preset_stop_loss_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_sl_price = round(preset_stop_loss_price, int(price_precision))
            data["presetStopLossPrice"] = str(formatted_sl_price)
        if preset_stop_surplus_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_tp_price = round(preset_stop_surplus_price, int(price_precision))
            data["presetStopSurplusPrice"] = str(formatted_tp_price)
        if preset_stop_loss_execute_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_sl_exec_price = round(preset_stop_loss_execute_price, int(price_precision))
            data["presetStopLossExecutePrice"] = str(formatted_sl_exec_price)
        if preset_stop_surplus_execute_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_tp_exec_price = round(preset_stop_surplus_execute_price, int(price_precision))
            data["presetStopSurplusExecutePrice"] = str(formatted_tp_exec_price)
        
        # Add client order ID if provided
        if client_oid:
            data["clientOid"] = client_oid
        
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to place order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to place order: {response}")
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open positions for the account.
        
        Args:
            symbol (str, optional): Specific symbol to query, or all if None
        
        Returns:
            List[Dict]: List of position data
        """
        endpoint = "/api/v2/mix/position/all-position"
        
        params = {
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT"  # Required field
        }
        
        if symbol:
            params["symbol"] = symbol
        
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get positions due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get positions: {response}")

    def modify_order(self, symbol: str, order_id: Optional[str] = None, client_oid: Optional[str] = None, 
                    new_size: Optional[float] = None, new_price: Optional[float] = None, 
                    new_client_oid: Optional[str] = None, new_preset_stop_loss_price: Optional[float] = None,
                    new_preset_stop_surplus_price: Optional[float] = None) -> Dict:
        """
        Modify an existing order on Bitget.
        
        Args:
            symbol (str): Trading symbol
            order_id (str, optional): Order ID to modify (either order_id or client_oid required)
            client_oid (str, optional): Client order ID to modify (either order_id or client_oid required)
            new_size (float, optional): New order size (required if modifying price)
            new_price (float, optional): New order price (required if modifying size)
            new_client_oid (str, optional): New client order ID (required if modifying size/price)
            new_preset_stop_loss_price (float, optional): New stop loss price (0 to remove)
            new_preset_stop_surplus_price (float, optional): New take profit price (0 to remove)
        
        Returns:
            Dict: Modify order response
        """
        endpoint = "/api/v2/mix/order/modify-order"
        
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES"
        }
        
        # Add order identification
        if order_id:
            data["orderId"] = order_id
        elif client_oid:
            data["clientOid"] = client_oid
        else:
            raise ValueError("Either orderId or clientOid must be provided")
        
        # Determine margin coin from symbol
        margin_coin = "USDT"
        if "USDC" in symbol:
            margin_coin = "USDC"
            
        # Add required fields
        data["marginCoin"] = margin_coin  # Required field
        
        # When modifying size and price, both must be provided and newClientOid is required
        size_price_provided = new_size is not None or new_price is not None
        if size_price_provided:
            if new_size is not None:
                # Validate and round the new size according to symbol's rules
                validated_new_size = self._validate_and_round_size(symbol, new_size)
                data["newSize"] = str(validated_new_size)  # Convert validated size to string as required by API
            if new_price is not None:
                # Use dynamic precision based on the symbol for new price
                symbol_precision = self._get_precision_for_symbol(symbol)
                price_precision = symbol_precision['price_precision']
                formatted_new_price = round(new_price, int(price_precision))
                data["newPrice"] = str(formatted_new_price)  # Convert rounded price to string as required by API
            if new_client_oid:
                data["newClientOid"] = new_client_oid
            else:
                # If we're modifying size/price, newClientOid is required
                if new_size is not None or new_price is not None:
                    raise ValueError("newClientOid is required when modifying size or price")
        
        # Add new preset stop loss price if provided
        if new_preset_stop_loss_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_sl_price = round(new_preset_stop_loss_price, int(price_precision))
            data["newPresetStopLossPrice"] = str(formatted_sl_price)
            
        # Add new preset take profit price if provided
        if new_preset_stop_surplus_price is not None:
            # Use dynamic precision based on the symbol
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_tp_price = round(new_preset_stop_surplus_price, int(price_precision))
            data["newPresetStopSurplusPrice"] = str(formatted_tp_price)
        
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to modify order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to modify order: {response}")

    def place_tpsl_order(self, symbol: str, plan_type: str, trigger_price: float, 
                        execute_price: Optional[float] = None, hold_side: str = "long",
                        size: Optional[float] = None, trigger_type: str = "mark_price",
                        client_oid: Optional[str] = None) -> Dict:
        """
        Place a stop-profit or stop-loss order (TPSL - Take Profit & Stop Loss).
        
        Args:
            symbol (str): Trading symbol
            plan_type (str): "profit_plan", "loss_plan", "moving_plan", "pos_profit", "pos_loss"
            trigger_price (float): Trigger price for the order
            execute_price (float, optional): Execution price (0 for market order, >0 for limit)
            hold_side (str): "long" or "short" for two-way mode, "buy"/"sell" for one-way mode
            size (float, optional): Order size (required for profit_plan, loss_plan, moving_plan)
            trigger_type (str): "fill_price" (transaction price) or "mark_price" (mark price)
            client_oid (str, optional): Custom order ID
            
        Returns:
            Dict: Response from the API
        """
        endpoint = "/api/v2/mix/order/place-tpsl-order"
        
        # Determine margin coin from symbol
        margin_coin = "USDT"
        if "USDC" in symbol:
            margin_coin = "USDC"
            
        # Use dynamic precision based on the symbol for trigger price
        symbol_precision = self._get_precision_for_symbol(symbol)
        price_precision = symbol_precision['price_precision']
        formatted_trigger_price = round(trigger_price, int(price_precision))
        
        # Prepare order data based on Bitget API v2 requirements
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",  # This should match Bitget's requirements
            "marginCoin": margin_coin,     # Required field
            "planType": plan_type,         # profit_plan, loss_plan, etc.
            "triggerPrice": str(formatted_trigger_price),  # Convert rounded price to string as required by API
            "holdSide": hold_side,         # long/short for two-way, buy/sell for one-way
            "triggerType": trigger_type    # fill_price or mark_price
        }
        
        # Add execute price (0 for market order)
        if execute_price is not None:
            # Use dynamic precision based on the symbol for execute price
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_execute_price = round(execute_price, int(price_precision))
            data["executePrice"] = str(formatted_execute_price)
        else:
            data["executePrice"] = "0"  # Market order execution
            
        # Add size if required (for profit_plan, loss_plan, moving_plan)
        if plan_type in ["profit_plan", "loss_plan", "moving_plan"]:
            if size is None:
                raise ValueError(f"Size is required for plan_type: {plan_type}")
            
            # Validate and round the size according to symbol's rules
            validated_size = self._validate_and_round_size(symbol, size)
            data["size"] = str(validated_size)
            
        # Add client order ID if provided
        if client_oid:
            data["clientOid"] = client_oid
            
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to place TPSL order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to place TPSL order: {response}")

    def modify_tpsl_order(self, order_id: Optional[str] = None, client_oid: Optional[str] = None,
                         symbol: str = "", trigger_price: float = 0.0,
                         execute_price: Optional[float] = None, size: Optional[float] = None,
                         range_rate: Optional[str] = None, trigger_type: str = "mark_price") -> Dict:
        """
        Modify an existing stop-profit or stop-loss order (TPSL).
        
        Args:
            order_id (str, optional): Order ID to modify (either order_id or client_oid required)
            client_oid (str, optional): Client order ID to modify (either order_id or client_oid required)
            symbol (str): Trading symbol
            trigger_price (float): New trigger price
            execute_price (float, optional): New execution price (0 for market order, >0 for limit)
            size (float, optional): New order size
            range_rate (str, optional): Callback range (for moving plans)
            trigger_type (str): "fill_price" (transaction price) or "mark_price" (mark price)
            
        Returns:
            Dict: Response from the API
        """
        endpoint = "/api/v2/mix/order/modify-tpsl-order"
        
        # Determine margin coin from symbol
        margin_coin = "USDT"
        if "USDC" in symbol:
            margin_coin = "USDC"
        
        # Use dynamic precision based on the symbol for trigger price
        symbol_precision = self._get_precision_for_symbol(symbol)
        price_precision = symbol_precision['price_precision']
        formatted_trigger_price = round(trigger_price, int(price_precision))
        
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,  # Required field
            "triggerPrice": str(formatted_trigger_price),  # Convert rounded price to string as required by API
            "triggerType": trigger_type
        }
        
        # Add order identification
        if order_id:
            data["orderId"] = order_id
        elif client_oid:
            data["clientOid"] = client_oid
        else:
            raise ValueError("Either orderId or clientOid must be provided")
        
        # Add optional fields if provided
        if execute_price is not None:
            # Use dynamic precision based on the symbol for execute price
            symbol_precision = self._get_precision_for_symbol(symbol)
            price_precision = symbol_precision['price_precision']
            formatted_execute_price = round(execute_price, int(price_precision))
            data["executePrice"] = str(formatted_execute_price)
        if size is not None:
            # Validate and round the size according to symbol's rules
            validated_size = self._validate_and_round_size(symbol, size)
            data["size"] = str(validated_size)
        if range_rate is not None:
            data["rangeRate"] = range_rate
            
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to modify TPSL order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to modify TPSL order: {response}")

    def cancel_tpsl_order(self, order_id: Optional[str] = None, client_oid: Optional[str] = None,
                         symbol: str = "", plan_type: str = "profit_plan") -> Dict:
        """
        Cancel an existing stop-profit or stop-loss order (TPSL).
        
        Args:
            order_id (str, optional): Order ID to cancel (either order_id or client_oid required)
            client_oid (str, optional): Client order ID to cancel (either order_id or client_oid required)
            symbol (str): Trading symbol
            plan_type (str): "profit_plan", "loss_plan", "moving_plan", etc.
            
        Returns:
            Dict: Response from the API
        """
        endpoint = "/api/v2/mix/order/cancel-tpsl-order"
        
        # Determine margin coin from symbol
        margin_coin = "USDT"
        if "USDC" in symbol:
            margin_coin = "USDC"
            
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,  # Required field
            "planType": plan_type
        }
        
        # Add order identification
        if order_id:
            data["orderId"] = order_id
        elif client_oid:
            data["clientOid"] = client_oid
        else:
            raise ValueError("Either orderId or clientOid must be provided")
            
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to cancel TPSL order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to cancel TPSL order: {response}")

    def get_tpsl_orders(self, symbol: str, plan_type: str = "profit_plan", is_stop: str = "yes") -> List[Dict]:
        """
        Get pending stop-profit or stop-loss orders (TPSL).
        
        Args:
            symbol (str): Trading symbol
            plan_type (str): "profit_plan", "loss_plan", "moving_plan", etc.
            is_stop (str): "yes" or "no" - whether to get stop orders or regular orders
            
        Returns:
            List[Dict]: List of pending TPSL orders
        """
        endpoint = "/api/v2/mix/order/orders-plan-pending"
        
        # Determine margin coin from symbol
        margin_coin = "USDT"
        if "USDC" in symbol:
            margin_coin = "USDC"
            
        params = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,  # Required field
            "planType": plan_type,
            "isTrigger": is_stop  # yes for stop orders, no for regular
        }
        
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get TPSL orders due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get TPSL orders: {response}")

    def get_history_positions(self, symbol: Optional[str] = None, start_time: Optional[int] = None, 
                             end_time: Optional[int] = None, limit: int = 20) -> List[Dict]:
        """
        Get historical positions for analysis.
        
        Args:
            symbol (str, optional): Specific symbol to query, or all if None
            start_time (int, optional): Start time in milliseconds
            end_time (int, optional): End time in milliseconds
            limit (int): Number of records to return (default 20, max 100)
            
        Returns:
            List[Dict]: List of historical position data
        """
        endpoint = "/api/v2/mix/position/history-position"
        
        params = {
            "productType": "USDT-FUTURES",
            "marginCoin": "USDT",  # Required field
            "limit": str(limit)
        }
        
        if symbol:
            params["symbol"] = symbol
            
        if start_time:
            params["startTime"] = str(start_time)
        if end_time:
            params["endTime"] = str(end_time)
            
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get history positions due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            # Return the list of positions from the response
            data = response.get('data', {})
            return data.get('list', []) if isinstance(data, dict) else []
        else:
            raise Exception(f"Failed to get history positions: {response}")