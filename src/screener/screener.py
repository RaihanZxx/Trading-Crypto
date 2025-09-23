import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
import json
from dotenv import load_dotenv

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.database import Database
from connectors.exchange_service import BitgetExchangeService
from utils.telegram import TelegramNotifier

# Load environment variables from .env file
load_dotenv()


class CryptoScreener:
    def __init__(self):
        """Initialize the crypto screener with all required services."""
        # Initialize database
        self.db = Database()
        
        # Initialize exchange service (credentials should be loaded from environment variables)
        self.exchange = BitgetExchangeService(
            api_key=os.getenv('BITGET_API_KEY'),
            secret_key=os.getenv('BITGET_SECRET_KEY'),
            passphrase=os.getenv('BITGET_PASSPHRASE')
        )
        
        # Initialize Telegram notifier (credentials should be loaded from environment variables)
        self.telegram = TelegramNotifier(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            chat_id=os.getenv('TELEGRAM_CHAT_ID'),
            message_thread_id=os.getenv('TELEGRAM_MESSAGE_THREAD_ID')
        )
        
        # Set timezone for WIB (UTC+7)
        self.wib_tz = timezone(timedelta(hours=7))
    
    def get_7am_timestamp(self, date: Optional[datetime] = None) -> str:
        """Get timestamp for 7:00 AM WIB (00:00 UTC) for given date or today."""
        if date is None:
            date = datetime.now(self.wib_tz)
        
        # Set time to 7:00 AM WIB (00:00 UTC)
        target_time = date.replace(hour=7, minute=0, second=0, microsecond=0)
        
        # Convert to UTC (subtract 7 hours)
        utc_time = target_time - timedelta(hours=7)
        
        return utc_time.strftime('%Y-%m-%d %H:%M:%S')
    
    def get_today_date_string(self) -> str:
        """Get today's date as string in YYYY-MM-DD format."""
        return datetime.now(self.wib_tz).strftime('%Y-%m-%d')
    
    def get_previous_business_day_date_string(self) -> str:
        """Get previous business day's date as string in YYYY-MM-DD format.
        For screener run on Tuesday 00:00 WIB, this will return Monday's date."""
        today = datetime.now(self.wib_tz)
        # Subtract 1 day for previous day
        previous_day = today - timedelta(days=1)
        return previous_day.strftime('%Y-%m-%d')
    
    def get_current_business_day_date_string(self) -> str:
        """Get current business day's date as string in YYYY-MM-DD format."""
        today = datetime.now(self.wib_tz)
        return today.strftime('%Y-%m-%d')
    
    def fetch_and_store_open_prices(self) -> None:
        """Fetch and store open prices for all futures symbols at 7:00 AM WIB."""
        # Determine which date's open prices we need based on current time
        current_time = datetime.now(self.wib_tz)
        current_hour = current_time.hour
        
        # If it's after 7 AM WIB, we need today's open prices
        # If it's before 7 AM WIB, we need yesterday's open prices
        if current_hour >= 7:
            open_price_date = self.get_current_business_day_date_string()
        else:
            open_price_date = self.get_previous_business_day_date_string()
        
        # Check if we already have open prices for the required date
        existing_prices = self.db.get_all_open_prices(open_price_date)
        if existing_prices:
            print(f"Open prices for {open_price_date} already exist in database. Skipping fetch.")
            return
        
        # Check if current time is around 7:00 AM WIB (with some tolerance)
        current_minute = current_time.minute
        
        # Only show warning if it's not around 7:00 AM WIB
        if not (current_hour == 7 and current_minute <= 30):
            print(f"Warning: No open prices found for {open_price_date} and not running at 7:00 AM WIB.")
            print("Fetching open prices now for accurate results...")
        
        print("Fetching all futures tickers...")
        try:
            tickers = self.exchange.get_all_tickers()
            print(f"Found {len(tickers)} futures tickers")
            
            # Create timestamp for 7:00 AM WIB on the required date
            target_date = datetime.strptime(open_price_date, '%Y-%m-%d')
            timestamp = self.get_7am_timestamp(target_date)
            print(f"Saving open prices for {open_price_date} at {timestamp} UTC...")
            
            count = 0
            for ticker in tickers:
                symbol = None
                try:
                    symbol = ticker['symbol']
                    # Skip symbols that already have prices
                    if symbol in existing_prices:
                        continue
                    
                    # Get open price from the ticker data (openUtc field)
                    if 'openUtc' in ticker and ticker['openUtc']:
                        open_price = float(ticker['openUtc'])
                        self.db.save_open_price(symbol, open_price, timestamp)
                        count += 1
                        
                        if count % 50 == 0:
                            print(f"Processed {count} symbols...")
                except Exception as e:
                    symbol_info = symbol if symbol else "unknown symbol"
                    print(f"Error processing ticker for {symbol_info}: {e}")
                    continue
            
            print(f"Successfully saved open prices for {count} symbols")
        except Exception as e:
            print(f"Error fetching tickers: {e}")

    def fetch_missing_open_prices(self, date: str) -> None:
        """Fetch and store open prices for all futures symbols for a specific date."""
        print(f"Fetching missing open prices for {date}...")
        
        # Check if we already have open prices for this date
        existing_prices = self.db.get_all_open_prices(date)
        if existing_prices:
            print(f"Open prices for {date} already exist in database. Skipping fetch.")
            return
        
        print("Fetching all futures tickers...")
        try:
            tickers = self.exchange.get_all_tickers()
            print(f"Found {len(tickers)} futures tickers")
            
            # Create timestamp for 7:00 AM WIB on the specified date
            target_date = datetime.strptime(date, '%Y-%m-%d')
            timestamp = self.get_7am_timestamp(target_date)
            print(f"Saving open prices for {date} at {timestamp} UTC...")
            
            count = 0
            for ticker in tickers:
                symbol = None
                try:
                    symbol = ticker['symbol']
                    # Skip symbols that already have prices
                    if symbol in existing_prices:
                        continue
                    
                    # Get open price from the ticker data (openUtc field)
                    if 'openUtc' in ticker and ticker['openUtc']:
                        open_price = float(ticker['openUtc'])
                        self.db.save_open_price(symbol, open_price, timestamp)
                        count += 1
                        
                        if count % 50 == 0:
                            print(f"Processed {count} symbols...")
                except Exception as e:
                    symbol_info = symbol if symbol else "unknown symbol"
                    print(f"Error processing ticker for {symbol_info}: {e}")
                    continue
            
            print(f"Successfully saved open prices for {count} symbols")
        except Exception as e:
            print(f"Error fetching tickers: {e}")
    
    def calculate_price_changes(self) -> List[Tuple[str, float, float, float]]:
        """Calculate price changes for all symbols compared to their open prices.
        Returns list of (symbol, open_price, last_price, change_percent)"""
        # Determine which date's open prices we need based on current time
        current_time = datetime.now(self.wib_tz)
        current_hour = current_time.hour
        
        # If it's after 7 AM WIB, we need today's open prices
        # If it's before 7 AM WIB, we need yesterday's open prices
        if current_hour >= 7:
            open_price_date = self.get_current_business_day_date_string()
        else:
            open_price_date = self.get_previous_business_day_date_string()
        
        # Get open prices from database
        open_prices = self.db.get_all_open_prices(open_price_date)
        if not open_prices:
            print(f"No open prices found in database for {open_price_date}")
            print(f"Attempting to fetch open prices for {open_price_date}...")
            # Try to fetch the missing open prices
            self.fetch_missing_open_prices(open_price_date)
            # Try again to get open prices
            open_prices = self.db.get_all_open_prices(open_price_date)
            if not open_prices:
                print(f"Still no open prices found in database for {open_price_date} after fetch attempt")
                return []
        
        # Get current prices from exchange
        print("Fetching current prices for all symbols...")
        tickers = self.exchange.get_all_tickers()
        
        # Calculate price changes
        price_changes = []
        for ticker in tickers:
            symbol = ticker['symbol']
            if symbol in open_prices:
                try:
                    open_price = open_prices[symbol]
                    # Use 'lastPr' instead of 'close' for the current price
                    if 'lastPr' not in ticker:
                        print(f"Warning: 'lastPr' key not found in ticker for {symbol}. Available keys: {list(ticker.keys())}")
                        continue
                    
                    last_price = float(ticker['lastPr'])
                    
                    # Calculate percentage change
                    if open_price > 0:
                        change_percent = ((last_price - open_price) / open_price) * 100
                        price_changes.append((symbol, open_price, last_price, change_percent))
                except Exception as e:
                    print(f"Error calculating price change for {symbol}: {e}")
                    continue
        
        # Sort by percentage change (highest first)
        price_changes.sort(key=lambda x: x[3], reverse=True)
        return price_changes
    
    def get_top_gainers_losers(self, price_changes: List[Tuple[str, float, float, float]], 
                              top_n: int = 10) -> Tuple[List[Tuple[str, float, float, float]], 
                                                       List[Tuple[str, float, float, float]]]:
        """Get top N gainers and losers from price changes.
        Returns (gainers, losers) where each is a list of (symbol, open_price, last_price, change_percent)"""
        # Top gainers (positive changes, highest first)
        gainers = [(symbol, open_price, last_price, change) for symbol, open_price, last_price, change in price_changes if change > 0]
        gainers = gainers[:top_n]
        
        # Top losers (negative changes, lowest first)
        losers = [(symbol, open_price, last_price, change) for symbol, open_price, last_price, change in price_changes if change < 0]
        losers = sorted(losers, key=lambda x: x[3])[:top_n]
        
        return gainers, losers
    
    def run_screener(self) -> None:
        """Run the complete screener workflow."""
        print("Starting crypto screener...")
        
        # Step 1: Fetch and store open prices if not already present
        self.fetch_and_store_open_prices()
        
        # Step 2: Calculate price changes
        print("Calculating price changes...")
        price_changes = self.calculate_price_changes()
        
        if not price_changes:
            print("No price changes calculated. Exiting.")
            return
        
        # Step 3: Get top gainers and losers
        print("Identifying top gainers and losers...")
        gainers, losers = self.get_top_gainers_losers(price_changes)
        
        # Step 4: Format results
        timestamp = datetime.now(self.wib_tz).strftime('%Y-%m-%d %H:%M:%S WIB')
        
        # Determine which date's open prices we used
        current_time = datetime.now(self.wib_tz)
        current_hour = current_time.hour
        
        if current_hour >= 7:
            open_price_date = self.get_current_business_day_date_string()
        else:
            open_price_date = self.get_previous_business_day_date_string()
        
        print(f"\n--- Screener Results at {timestamp} (Using open prices from {open_price_date} 07:00 WIB) ---")
        if gainers:
            print("\n🚀 Top 10 Gainers:")
            for i, (symbol, open_price, last_price, change) in enumerate(gainers, 1):
                print(f"{i:2d}. {symbol:<12} {open_price:>8.4f} -> {last_price:>8.4f} {change:+.2f}%")
        
        if losers:
            print("\n❄️  Top 10 Losers:")
            for i, (symbol, open_price, last_price, change) in enumerate(losers, 1):
                print(f"{i:2d}. {symbol:<12} {open_price:>8.4f} -> {last_price:>8.4f} {change:+.2f}%")
        
        # Step 5: Send notification via Telegram
        print("\nSending results to Telegram...")
        # Check if Telegram credentials are configured
        if not self.telegram.bot_token or not self.telegram.chat_id:
            print("⚠️  Telegram bot token or chat ID not configured. Skipping notification.")
            print("💡 To enable Telegram notifications, configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file.")
        else:
            success = self.telegram.send_screener_results(gainers, losers, timestamp)
            if success:
                print("✅ Results sent to Telegram successfully!")
            else:
                print("❌ Failed to send results to Telegram")
        
        # Step 6: Save results to database
        try:
            gainers_str = json.dumps(gainers)
            losers_str = json.dumps(losers)
            self.db.save_screener_result(timestamp, gainers_str, losers_str)
            print("💾 Results saved to database")
        except Exception as e:
            print(f"❌ Error saving results to database: {e}")

def main():
    """Main entry point for the screener."""
    screener = CryptoScreener()
    screener.run_screener()

if __name__ == "__main__":
    main()