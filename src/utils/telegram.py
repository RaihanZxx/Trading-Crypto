import requests
import os
import json
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None, message_thread_id: Optional[str] = None):
        """Initialize Telegram notifier with bot token, chat ID, and optional message thread ID."""
        self.bot_token = bot_token or ""
        self.chat_id = chat_id or ""
        self.message_thread_id = message_thread_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.state_file = "data/telegram_state.json"
    
    def _load_state(self) -> dict:
        """Load Telegram message state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading Telegram state: {e}")
        return {}
    
    def _save_state(self, state: dict):
        """Save Telegram message state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            print(f"Error saving Telegram state: {e}")
    
    def _delete_message(self, message_id: int) -> bool:
        """Delete a message by its ID."""
        if not self.bot_token or not self.chat_id:
            return False
            
        try:
            url = f"{self.base_url}/deleteMessage"
            data = {
                "chat_id": self.chat_id,
                "message_id": message_id
            }
            
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("ok", False)
            else:
                print(f"Failed to delete Telegram message. Status code: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error deleting Telegram message: {e}")
            return False
    
    def send_message(self, message: str) -> Optional[int]:
        """Send message to Telegram chat, optionally to a specific thread. Returns message ID if successful."""
        if not self.bot_token or not self.chat_id:
            print("Telegram bot token or chat ID not configured. Skipping notification.")
            return None
            
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            # Add message thread ID if provided (for topic groups)
            if self.message_thread_id:
                data["message_thread_id"] = self.message_thread_id
            
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return result["result"]["message_id"]
                else:
                    print(f"Failed to send Telegram message: {result.get('description')}")
                    return None
            else:
                print(f"Failed to send Telegram message. Status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return None
    
    def send_screener_results(self, gainers: list, losers: list, timestamp: str) -> bool:
        """Send screener results to Telegram, deleting previous message if exists."""
        if not gainers and not losers:
            message = "🚨 *Crypto Screener Report* 🚨\n\n"
            message += f"⏰ *Timestamp:* {timestamp}\n\n"
            message += "No significant gainers or losers found."
        else:
            message = "🚀 *Crypto Screener Report* 🚀\n\n"
            message += f"⏰ *Timestamp:* {timestamp}\n\n"
            
            if gainers:
                message += "🔥 *Top 10 Gainers:*\n"
                for i, (symbol, open_price, last_price, change) in enumerate(gainers, 1):
                    message += f"{i}. {symbol}: {change:+.2f}%\n"
                message += "\n"
            
            if losers:
                message += "❄️ *Top 10 Losers:*\n"
                for i, (symbol, open_price, last_price, change) in enumerate(losers, 1):
                    message += f"{i}. {symbol}: {change:+.2f}%\n"
        
        # Load previous message state
        state = self._load_state()
        thread_key = f"{self.chat_id}_{self.message_thread_id or 'main'}"
        previous_message_id = state.get(thread_key)
        
        # Delete previous message if it exists
        if previous_message_id:
            print(f"Deleting previous screener message (ID: {previous_message_id})")
            self._delete_message(previous_message_id)
        
        # Send new message
        message_id = self.send_message(message)
        
        if message_id:
            # Save new message ID to state
            state[thread_key] = message_id
            self._save_state(state)
            print(f"New screener message sent (ID: {message_id})")
            return True
        else:
            print("Failed to send new screener message")
            return False