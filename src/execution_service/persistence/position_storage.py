import json
import os
import threading
from typing import Dict, Any


def _ensure_data_directory(positions_file: str):
    """Create data directory if it doesn't exist."""
    data_dir = os.path.dirname(positions_file)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)


def _load_persisted_positions(positions_file: str, active_positions: Dict[str, Any], lock, exchange, monitor_callback):
    """Load persisted active positions from file at startup."""
    try:
        if os.path.exists(positions_file):
            with open(positions_file, 'r') as f:
                persisted_positions = json.load(f)
                
            # Convert string keys back to appropriate types if needed
            with lock:
                active_positions.update(persisted_positions)
                print(f"[Python Executor] Loaded {len(active_positions)} persisted positions from {positions_file}")
            
            # Restart monitoring for each loaded position
            for symbol in active_positions:
                print(f"[Python Executor] Restarting monitoring for persisted position: {symbol}")
                monitoring_thread = threading.Thread(
                    target=monitor_callback, 
                    args=(symbol,), 
                    daemon=True
                )
                monitoring_thread.start()
                print(f"[Python Executor] Resumed monitoring thread for {symbol}")
        else:
            print(f"[Python Executor] Positions file {positions_file} not found. Starting with empty positions.")
    except Exception as e:
        print(f"[Python Executor] Error loading persisted positions: {e}")
        # If there's an error loading, start with empty positions
        with lock:
            active_positions.clear()


def _save_persisted_positions(positions_file: str, active_positions: Dict[str, Any], lock):
    """Save active positions to file."""
    try:
        with lock:
            # Create a copy to avoid holding the lock during file I/O
            positions_to_save = active_positions.copy()
        
        with open(positions_file, 'w') as f:
            json.dump(positions_to_save, f, indent=2)
            
        print(f"[Python Executor] Saved {len(positions_to_save)} active positions to {positions_file}")
    except Exception as e:
        print(f"[Python Executor] Error saving positions to file: {e}")