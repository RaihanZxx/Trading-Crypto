use std::time::Duration;
use tokio;
use tokio::time;
use pyo3::prelude::*;

/// Position monitor service that periodically checks positions via Python
pub struct PositionMonitorService {
    interval_secs: u64,
}

impl PositionMonitorService {
    /// Create a new position monitor service
    pub fn new(interval_secs: u64) -> Self {
        Self { interval_secs }
    }

    /// Start the position monitoring service
    pub async fn start(&self) {
        println!("[POSITION MONITOR] Starting position monitoring service with {} second intervals", self.interval_secs);
        
        let mut interval = time::interval(Duration::from_secs(self.interval_secs));
        
        loop {
            interval.tick().await;
            
            if let Err(e) = self.check_positions().await {
                eprintln!("[POSITION MONITOR] Error checking positions: {}", e);
            }
        }
    }

    /// Check positions by calling Python TradeManager
    async fn check_positions(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        println!("[POSITION MONITOR] Checking positions...");
        
        Python::with_gil(|py| -> PyResult<()> {
            // Add the current directory to Python's path so it can find local modules
            let sys = PyModule::import_bound(py, "sys")?;
            let sys_path = sys.getattr("path")?;
            sys_path.call_method1("insert", (0, "."))?;
            
            let trade_manager = PyModule::import_bound(py, "execution_service.manager")?;
            
            // Call the get_active_positions method
            let result = trade_manager.getattr("trade_manager")?.getattr("get_active_positions")?.call0()?;
            
            // Extract the positions dictionary
            let positions_dict = result.downcast::<pyo3::types::PyDict>()?;
            
            // Check if there are active positions
            let positions_count = positions_dict.len();
            if positions_count > 0 {
                println!("[POSITION MONITOR] Found {} active position(s)", positions_count);
                
                // Print each active position
                for (symbol, position_data) in positions_dict.iter() {
                    let symbol_str = symbol.extract::<String>().unwrap_or_else(|_| "Unknown".to_string());
                    if let Ok(position_data_dict) = position_data.downcast::<pyo3::types::PyDict>() {
                        // Extract position details with proper error handling
                        let entry_price = match position_data_dict.get_item("entry_price") {
                            Ok(Some(value)) => value.extract::<f64>().unwrap_or(0.0),
                            _ => 0.0
                        };
                        
                        let size = match position_data_dict.get_item("size") {
                            Ok(Some(value)) => value.extract::<f64>().unwrap_or(0.0),
                            _ => 0.0
                        };
                        
                        let side = match position_data_dict.get_item("side") {
                            Ok(Some(value)) => value.extract::<String>().unwrap_or_else(|_| "unknown".to_string()),
                            _ => "unknown".to_string()
                        };
                        
                        let stop_loss = match position_data_dict.get_item("stop_loss_price") {
                            Ok(Some(value)) => value.extract::<f64>().unwrap_or(0.0),
                            _ => 0.0
                        };
                        
                        let take_profit = match position_data_dict.get_item("take_profit_price") {
                            Ok(Some(value)) => value.extract::<f64>().unwrap_or(0.0),
                            _ => 0.0
                        };
                        
                        println!("[POSITION MONITOR] Position: {} | Side: {} | Size: {} | Entry: {} | SL: {} | TP: {}", 
                                 symbol_str, side, size, entry_price, stop_loss, take_profit);
                    } else {
                        println!("[POSITION MONITOR] Position data for {} is not a dictionary", symbol_str);
                    }
                }
            } else {
                println!("[POSITION MONITOR] No active positions found");
            }
            
            Ok(())
        }).map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>) // Remove the ? here
    }

    /// Check if a position exists for a given symbol by calling Python TradeManager
    pub async fn check_position_exists(&self, symbol: &str) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        println!("[POSITION MONITOR] Checking if position exists for symbol: {}", symbol);
        
        let result = Python::with_gil(|py| -> PyResult<bool> {
            // Add the current directory to Python's path so it can find local modules
            let sys = PyModule::import_bound(py, "sys")?;
            let sys_path = sys.getattr("path")?;
            sys_path.call_method1("insert", (0, "."))?;
            
            let trade_manager = PyModule::import_bound(py, "execution_service.manager")?;
            
            // Call the get_active_positions method
            let result = trade_manager.getattr("trade_manager")?.getattr("get_active_positions")?.call0()?;
            
            // Extract the positions dictionary
            let positions_dict = result.downcast::<pyo3::types::PyDict>()?;
            
            // Check if the symbol exists in the positions dictionary
            let position_exists = positions_dict.contains(symbol)?;
            
            if position_exists {
                println!("[POSITION MONITOR] Position found for symbol: {}", symbol);
            } else {
                println!("[POSITION MONITOR] No position found for symbol: {}", symbol);
            }
            
            Ok(position_exists)
        }).map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        
        Ok(result)
    }
}