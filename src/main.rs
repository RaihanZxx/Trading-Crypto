use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use std::collections::HashMap;
use pyo3::prelude::*;

// Define the TradingSignal structure
#[derive(Debug, Clone)]
pub struct TradingSignal {
    pub symbol: String,
    pub signal_type: String,  // e.g., "StrongBuy", "StrongSell"
    pub price: f64,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

// Function to call Python Screener
fn call_python_screener() -> PyResult<Vec<String>> {
    Python::with_gil(|py| {
        let sys = py.import_bound("sys")?;
        let sys_path = sys.getattr("path")?;
        sys_path.call_method1("append", (".",))?;
        
        let screener = PyModule::import_bound(py, "screener.screener")?;
        let result: Vec<String> = screener.getattr("get_top_candidates")?.call0()?.extract()?;
        Ok(result)
    })
}

// Function to call Python Execution Service
fn call_python_executor(signal: TradingSignal) -> PyResult<()> {
    Python::with_gil(|py| {
        let sys = py.import_bound("sys")?;
        let sys_path = sys.getattr("path")?;
        sys_path.call_method1("append", (".",))?;
        
        let executor = PyModule::import_bound(py, "execution_service.manager")?;
        let signal_dict = PyDict::new_bound(py);
        signal_dict.set_item("symbol", &signal.symbol)?;
        signal_dict.set_item("signal_type", &signal.signal_type)?;
        signal_dict.set_item("price", signal.price)?;
        signal_dict.set_item("timestamp", signal.timestamp.to_rfc3339())?;
        
        executor.getattr("handle_trade_signal")?.call1((signal_dict,))?;
        Ok(())
    })
}

// Function to establish WebSocket connection and analyze data for a specific symbol
// This function now uses the existing WebSocket implementation from connectors/websocket.rs

use crate::engine::{OFIEngine as InternalOFIEngine, run_analysis_with_config};
use crate::signals::{StrategyParams, SignalType};
use crate::config::OFIConfig;

async fn analyze_symbol_data(
    symbol: String,
    signal_tx: mpsc::Sender<TradingSignal>,
    mut shutdown_rx: mpsc::Receiver<()>
) -> Result<(), Box<dyn std::error::Error>> {
    // Load configuration
    let config = match OFIConfig::from_default_config() {
        Ok(config) => config,
        Err(e) => {
            eprintln!("[TASK] Failed to load configuration for {}: {}", symbol, e);
            return Err(e.into());
        }
    };

    // Create strategy parameters with default values
    let params = StrategyParams {
        imbalance_threshold: config.default_imbalance_threshold,
        absorption_threshold: config.default_absorption_threshold,
        delta_threshold: config.default_delta_threshold,
        lookback_period_ms: config.default_lookback_period_ms,
    };

    // Create an OFIEngine instance for this symbol
    let engine = InternalOFIEngine::new(params, config);

    println!("[TASK] Starting WebSocket analysis for {}", symbol);

    loop {
        tokio::select! {
            // Check for shutdown signal
            _ = shutdown_rx.recv() => {
                println!("[TASK] Shutdown signal received for {}", symbol);
                break;
            },
            // Run the WebSocket analysis for a short duration and check for signals
            result = run_analysis_with_config(
                symbol.clone(),
                engine.config().default_imbalance_threshold,
                engine.config().analysis_duration_per_cycle_ms, // Use config value for analysis duration per cycle
                engine.config().default_delta_threshold,
                engine.config().default_lookback_period_ms,
                engine.config().clone()
            ) => {
                match result {
                    Ok(Some(signal)) => {
                        // Convert internal signal to our TradingSignal format
                        let new_signal = TradingSignal {
                            symbol: signal.symbol,
                            signal_type: format!("{:?}", signal.signal_type),
                            price: signal.price,
                            timestamp: chrono::Utc::now(),
                        };
                        
                        if let Err(e) = signal_tx.send(new_signal).await {
                            eprintln!("[TASK] Failed to send signal for {}: {}", symbol, e);
                            break;
                        }
                    }
                    Ok(None) => {
                        // No signal found in this analysis period, continue
                        println!("[TASK] No signal found for {} in this analysis period", symbol);
                    }
                    Err(e) => {
                        eprintln!("[TASK] Error during analysis for {}: {}", symbol, e);
                        // Continue the loop despite the error
                    }
                }
            }
        }
        
        // Small delay to avoid busy loop
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    Ok(())
}

// Function to spawn an analysis task for a specific symbol
async fn spawn_analysis_task(
    symbol: String,
    signal_tx: mpsc::Sender<TradingSignal>,
    shutdown_rx: mpsc::Receiver<()>
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        println!("[TASK] Starting analysis task for {}", symbol);
        
        if let Err(e) = analyze_symbol_data(symbol.clone(), signal_tx, shutdown_rx).await {
            eprintln!("[TASK] Error analyzing {}: {}", symbol, e);
        }
        
        println!("[TASK] Analysis task for {} terminated", symbol);
    })
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    env_logger::init();
    
    // Channel for communication from task analysis to main loop
    let (signal_tx, mut signal_rx) = mpsc::channel(100);
    
    // HashMap to store handles of running tasks
    let mut running_tasks: HashMap<String, tokio::task::JoinHandle<()>> = HashMap::new();
    
    // Timer for refreshing watchlist every 15 minutes (900 seconds)
    let mut watchlist_refresh_timer = interval(Duration::from_secs(900));
    
    println!("[SENTINEL] OFI Sentinel Dimulai. Menunggu siklus pertama...");
    
    loop {
        tokio::select! {
            // Branch 1: Timer for refreshing watchlist reached
            _ = watchlist_refresh_timer.tick() => {
                println!("[SENTINEL] Waktunya menyegarkan watchlist...");
                
                // Call Python Screener
                let new_candidates = match call_python_screener() {
                    Ok(candidates) => {
                        println!("[SENTINEL] Dapatkan kandidat baru: {:?}", candidates);
                        candidates
                    },
                    Err(e) => {
                        eprintln!("[SENTINEL] Gagal memanggil screener Python: {}", e);
                        continue;
                    }
                };

                // Compare new_candidates with running_tasks
                // Stop tasks for symbols no longer in candidates
                let mut to_remove = Vec::new();
                for (symbol, handle) in &running_tasks {
                    if !new_candidates.contains(symbol) {
                        println!("[SENTINEL] Menghentikan task untuk: {}", symbol);
                        handle.abort();
                        to_remove.push(symbol.clone());
                    }
                }
                
                // Actually remove the handles
                for symbol in to_remove {
                    running_tasks.remove(&symbol);
                }

                // Start tasks for new candidates not already running
                for candidate in &new_candidates {
                    if !running_tasks.contains_key(candidate) {
                        println!("[SENTINEL] Memulai task baru untuk: {}", candidate);
                        
                        // Create shutdown channel for this task
                        let (_shutdown_tx, shutdown_rx) = mpsc::channel(1);
                        
                        // Spawn the analysis task
                        let task_handle = spawn_analysis_task(
                            candidate.clone(),
                            signal_tx.clone(),
                            shutdown_rx
                        ).await;
                        
                        running_tasks.insert(candidate.clone(), task_handle);
                    }
                }
            },

            // Branch 2: Receive signal from one of the analysis tasks
            Some(signal) = signal_rx.recv() => {
                println!("[SENTINEL] Menerima sinyal: {:?}", signal);
                
                // Call Python Execution Service
                if let Err(e) = call_python_executor(signal) {
                    eprintln!("[SENTINEL] Gagal memanggil executor Python: {}", e);
                }
            }
        }
    }
}