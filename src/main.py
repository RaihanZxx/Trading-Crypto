import os
import sys
from dotenv import load_dotenv

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from screener.screener import main

# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    main()