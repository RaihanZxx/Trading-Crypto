import requests
import hmac
import hashlib
import base64
import time
import json
from typing import Dict, List, Optional
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
        
        # Prepare request path and query string
        request_path = endpoint
        query_string = ""
        body = ""
        
        if params:
            query_string = urlencode(params)
            
        if data:
            body = json.dumps(data)
            
        # Sign the request
        signature = self._sign_request(timestamp, method, request_path, query_string, body)
        
        # Prepare headers
        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': str(timestamp),
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        # Build URL
        url = self.base_url + request_path
        if query_string:
            url += "?" + query_string
            
        # Make request with error handling
        def _request():
            response = None  # Initialize response to avoid "possibly unbound" error
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, data=body, timeout=30)
            
            # Check if request was successful
            if response is not None:
                response.raise_for_status()
                return response.json()
            else:
                # Return a default error response instead of raising an exception
                return {"code": "request_failed", "message": "Failed to make request"}
        
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
                   client_oid: Optional[str] = None) -> Dict:
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
        
        Returns:
            Dict: Order response
        """
        endpoint = "/api/v2/mix/order/place-order"
        
        # Validate required parameters
        if side.lower() not in ["buy", "sell"]:
            raise ValueError(f"Side must be 'buy' or 'sell', got: {side}")
        
        if order_type.lower() not in ["limit", "market"]:
            raise ValueError(f"Order type must be 'limit' or 'market', got: {order_type}")
        
        # Prepare order data
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginMode": "crossed",  # or "fixed" based on your strategy
            "side": side.lower(),
            "orderType": order_type.lower(),
            "size": str(size),
            "timeInForceValue": time_in_force
        }
        
        # Add price for limit orders
        if order_type.lower() == "limit":
            if price is None:
                raise ValueError("Price is required for limit orders")
            data["price"] = str(price)
        
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
    
    def place_stop_market_order(self, symbol: str, side: str, trigger_price: float, 
                               size: float, trigger_type: str = "market_price") -> Dict:
        """
        Place a stop market order (conditional order) on Bitget.
        
        Args:
            symbol (str): Trading symbol (e.g., "BTCUSDT")
            side (str): "buy" or "sell" - for stop orders, this is opposite of the initial position
            trigger_price (float): Price that triggers the order
            size (float): Order size in contracts
            trigger_type (str): "market_price" or "mark_price" - what price feeds the trigger
        
        Returns:
            Dict: Stop order response
        """
        endpoint = "/api/v2/mix/order/place-trigger-order"
        
        # Validate required parameters
        if side.lower() not in ["buy", "sell"]:
            raise ValueError(f"Side must be 'buy' or 'sell', got: {side}")
        
        if trigger_type not in ["market_price", "mark_price"]:
            raise ValueError(f"Trigger type must be 'market_price' or 'mark_price', got: {trigger_type}")
        
        # Determine trigger side based on what we want to close position
        # If we have a long position (bought), we want to sell when price goes down (stop loss)
        # If we have a short position (sold), we want to buy when price goes up (stop loss)
        trigger_side = "close_long" if side.lower() == "sell" else "close_short"
        
        # Prepare stop order data
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginMode": "crossed",  # or "fixed" based on your strategy
            "side": trigger_side,
            "orderType": "market",
            "triggerType": trigger_type,
            "triggerPrice": str(trigger_price),
            "size": str(size),
            "executePrice": "",  # Empty for market orders
        }
        
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to place stop order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to place stop order: {response}")
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open positions for the account.
        
        Args:
            symbol (str, optional): Specific symbol to query, or all if None
        
        Returns:
            List[Dict]: List of position data
        """
        endpoint = "/api/v2/mix/position/single-position"
        
        params = {
            "productType": "USDT-FUTURES",
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
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open orders for the account.
        
        Args:
            symbol (str, optional): Specific symbol to query, or all if None
        
        Returns:
            List[Dict]: List of open order data
        """
        endpoint = "/api/v2/mix/order/current-orders"
        
        params = {
            "productType": "USDT-FUTURES",
        }
        
        if symbol:
            params["symbol"] = symbol
        
        response = self._make_request('GET', endpoint, params)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to get open orders due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', [])
        else:
            raise Exception(f"Failed to get open orders: {response}")
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """
        Cancel a specific order.
        
        Args:
            symbol (str): Trading symbol
            order_id (str): Order ID to cancel
        
        Returns:
            Dict: Cancel order response
        """
        endpoint = "/api/v2/mix/order/cancel-order"
        
        data = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "orderId": order_id
        }
        
        response = self._make_request('POST', endpoint, data=data)
        
        # Check for error responses
        if isinstance(response, dict) and response.get('code') in ['connection_error', 'timeout_error', 'request_error', 'unknown_error']:
            raise Exception(f"Failed to cancel order due to network error: {response.get('message')}")
        
        if response.get('code') == '00000':
            return response.get('data', {})
        else:
            raise Exception(f"Failed to cancel order: {response}")