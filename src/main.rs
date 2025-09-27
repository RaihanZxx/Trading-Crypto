use tokio::sync::{mpsc, Semaphore};
use tokio::time::{interval, Duration as TokioDuration};
use std::collections::HashMap;
use std::sync::Arc;
use std::thread;
use std::sync::mpsc as sync_mpsc;
use std::time::Duration as StdDuration;

// Import colored crate for modern colored logging
use colored::*;
use log::{error, info, warn};

// Import from our library crate
use ofi_engine_rust::config::OFIConfig;
use ofi_engine_rust::engine::OFIEngine;
use ofi_engine_rust::signals::StrategyParams;
use ofi_engine_rust::websocket::run_websocket_manager;

use pyo3::prelude::*;

// Define the TradingSignal structure for the main flow.
// This is kept separate to decouple the main application logic from the library's internal types.
#[derive(Debug, Clone)]
pub struct TradingSignal {
    pub symbol: String,
    pub signal_type: String, // e.g., "StrongBuy", "StrongSell"
    pub price: f64,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

// Function to call Python Screener
fn call_python_screener() -> PyResult<Vec<String>> {
    Python::with_gil(|py| {
        let screener = PyModule::import_bound(py, "screener.screener")?;
        match screener.getattr("get_top_candidates")?.call0() {
            Ok(result) => result.extract(),
            Err(e) => {
                error!("[SENTINEL-ERROR] Panggilan Python ke screener gagal:");
                e.print_and_set_sys_last_vars(py);
                Err(e)
            }
        }
    })
}

// Function to call Python Execution Service with timeout
fn call_python_executor(signal: TradingSignal) -> PyResult<()> {
    let (tx, rx) = sync_mpsc::channel();
    
    // Spawn a thread to execute the Python call
    let signal_clone = signal.clone();
    let _handle = thread::spawn(move || {
        let result = Python::with_gil(|py| {
            let executor = PyModule::import_bound(py, "execution_service.manager")?;
            let signal_dict = pyo3::types::PyDict::new_bound(py);
            signal_dict.set_item("symbol", &signal_clone.symbol)?;
            signal_dict.set_item("signal_type", &signal_clone.signal_type)?;
            signal_dict.set_item("price", signal_clone.price)?;
            signal_dict.set_item("timestamp", signal_clone.timestamp.to_rfc3339())?;

            let result = executor.getattr("handle_trade_signal")?.call1((signal_dict,))?;

            if let Ok(result_dict) = result.downcast::<pyo3::types::PyDict>() {
                if let Ok(Some(status)) = result_dict.get_item("status") {
                    if let Ok(status_str) = status.extract::<String>() {
                        if status_str == "error" {
                            let reason = match result_dict.get_item("reason") {
                                Ok(Some(r)) => r.extract().unwrap_or_else(|_| "Could not extract reason".to_string()),
                                Ok(None) => "No reason provided".to_string(),
                                Err(_) => "Failed to get reason key from Python dict".to_string(),
                            };
                            warn!("[SENTINEL-WARN] Eksekusi trade gagal di Python dengan alasan: {}", reason);
                        }
                    }
                }
            }
            Ok(())
        });
        
        // Send the result through the channel
        let _ = tx.send(result);
    });
    
    // Wait for the thread to complete with a timeout
    match rx.recv_timeout(StdDuration::from_secs(30)) {
        Ok(result) => result,
        Err(_) => {
            warn!("[SENTINEL-WARN] Python executor call timed out after 30 seconds for symbol {}", signal.symbol);
            // Note: We can't actually kill the thread here, but at least we don't block the main loop
            Ok(())
        }
    }
}

// Function to call Python Position Monitor with timeout
fn call_python_position_monitor() -> PyResult<()> {
    let (tx, rx) = sync_mpsc::channel();
    
    // Spawn a thread to execute the Python call
    let _handle = thread::spawn(move || {
        let result = Python::with_gil(|py| {
            let executor = PyModule::import_bound(py, "execution_service.manager")?;
            
            let result = executor.getattr("run_periodic_position_check")?.call0()?;

            if let Ok(result_dict) = result.downcast::<pyo3::types::PyDict>() {
                if let Ok(Some(status)) = result_dict.get_item("status") {
                    if let Ok(status_str) = status.extract::<String>() {
                        if status_str == "error" {
                            let reason = match result_dict.get_item("reason") {
                                Ok(Some(r)) => r.extract().unwrap_or_else(|_| "Could not extract reason".to_string()),
                                Ok(None) => "No reason provided".to_string(),
                                Err(_) => "Failed to get reason key from Python dict".to_string(),
                            };
                            warn!("[SENTINEL-WARN] Position monitoring failed in Python with reason: {}", reason);
                        }
                    }
                }
            }
            Ok(())
        });
        
        // Send the result through the channel
        let _ = tx.send(result);
    });
    
    // Wait for the thread to complete with a timeout
    match rx.recv_timeout(StdDuration::from_secs(30)) {
        Ok(result) => result,
        Err(_) => {
            warn!("[SENTINEL-WARN] Python position monitor call timed out after 30 seconds");
            Ok(())
        }
    }
}
/// This task uses the robust `run_websocket_manager` for continuous data analysis.
async fn spawn_analysis_task(
    symbol: String,
    signal_tx: mpsc::Sender<TradingSignal>,
    mut shutdown_rx: mpsc::Receiver<()>
) {
    info!("[TASK] Starting analysis task for {}", symbol);

    // 1. Initialize configuration and engine for this symbol
    let config = match OFIConfig::from_default_config() {
        Ok(c) => c,
        Err(e) => {
            error!("[TASK-ERROR] Gagal memuat config untuk {}: {}. Task dihentikan.", symbol, e);
            return;
        }
    };

    let params = StrategyParams {
        imbalance_threshold: config.imbalance_threshold,
        absorption_threshold: config.absorption_threshold,
        delta_threshold: config.delta_threshold,
        lookback_period_ms: config.lookback_period_ms,
        market_condition_multiplier: 1.0, // Default multiplier
    };
    let engine = OFIEngine::new(params, config.clone());

    // 2. Start the websocket manager and get the receiver for library-internal signals
    let mut lib_signal_rx = run_websocket_manager(symbol.clone(), engine).await;
    info!("[TASK] WebSocket manager running for {}. Waiting for signals...", symbol);

    // 3. Main loop for this task: listen for signals or shutdown command
    loop {
        tokio::select! {
            // Listen for shutdown signal
            _ = shutdown_rx.recv() => {
                info!("[TASK] Menerima sinyal shutdown untuk {}. Keluar...", symbol);
                break; // Exit the loop to terminate the task
            },

            // Listen for a signal from the websocket manager
            Some(lib_signal) = lib_signal_rx.recv() => {
                info!("[TASK] Signal ditemukan untuk {}: {:?}", symbol, lib_signal.signal_type);

                // Convert from the library's signal type to the main application's signal type
                let app_signal = TradingSignal {
                    symbol: lib_signal.symbol,
                    signal_type: format!("{:?}", lib_signal.signal_type),
                    price: lib_signal.price,
                    timestamp: chrono::Utc::now(), // Use current time for the final signal event
                };

                // Forward the converted signal to the main sentinel loop
                if signal_tx.send(app_signal).await.is_err() {
                    error!("[TASK] Gagal mengirim sinyal ke Sentinel untuk {}: channel ditutup. Task dihentikan.", symbol);
                    break; // Exit if the main receiver is dropped
                }
            }
        }
    }
    info!("[TASK] Analysis task for {} has been terminated.", symbol);
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Install the default crypto provider
    if let Err(e) = rustls::crypto::ring::default_provider().install_default() {
        eprintln!("Failed to install default crypto provider: {:?}", e);
    }
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format(|buf, record| {
            use std::io::Write;
            let timestamp = chrono::Local::now().format("%H:%M:%S");
            let level = record.level();
            let level_str = match level {
                log::Level::Error => "ERROR".red().bold(),
                log::Level::Warn => "WARN ".yellow().bold(),
                log::Level::Info => "INFO ".green().bold(),
                log::Level::Debug => "DEBUG".blue().bold(),
                log::Level::Trace => "TRACE".cyan().bold(),
            };
            writeln!(buf, "[{}] [{}] [{}] {}", timestamp, level_str, record.target(), record.args())
        })
        .init();

    let config = OFIConfig::from_default_config()?;
    let max_concurrent_tasks = config.max_concurrent_websocket_connections.unwrap_or(20);
    let task_semaphore = Arc::new(Semaphore::new(max_concurrent_tasks));
    let (signal_tx, mut signal_rx) = mpsc::channel(100);
    let mut running_tasks: HashMap<String, (tokio::task::JoinHandle<()>, mpsc::Sender<()>)> = HashMap::new();
    let mut watchlist_refresh_timer = interval(TokioDuration::from_secs(900));

    info!("[SENTINEL] Setting up periodic position monitoring...");
    let mut position_monitor_timer = interval(TokioDuration::from_secs(60)); // Every 60 seconds

    info!("[SENTINEL] OFI Sentinel Dimulai. Maksimum koneksi simultan: {}", max_concurrent_tasks);

    loop {
        tokio::select! {
            _ = watchlist_refresh_timer.tick() => {
                info!("[SENTINEL] Waktunya menyegarkan watchlist...");
                let new_candidates = call_python_screener().unwrap_or_else(|e| {
                    error!("[SENTINEL] Gagal mendapatkan kandidat dari Python: {}. Menggunakan watchlist kosong.", e);
                    Vec::new()
                });

                let mut symbols_to_stop = Vec::new();
                for symbol in running_tasks.keys() {
                    if !new_candidates.contains(symbol) {
                        symbols_to_stop.push(symbol.clone());
                    }
                }

                for symbol in symbols_to_stop {
                    info!("[SENTINEL] Menghentikan task untuk simbol: {}", symbol);
                    if let Some((handle, shutdown_tx)) = running_tasks.remove(&symbol) {
                        let _ = shutdown_tx.send(()).await;
                        match tokio::time::timeout(TokioDuration::from_secs(5), handle).await {
                            Ok(_) => info!("[SENTINEL] Task untuk {} berhasil dihentikan.", symbol),
                            Err(_) => warn!("[SENTINEL-WARN] Task untuk {} gagal berhenti dalam 5 detik.", symbol),
                        }
                    }
                }

                for candidate in &new_candidates {
                    if !running_tasks.contains_key(candidate) {
                        info!("[SENTINEL] Memulai task baru untuk: {}", candidate);
                        let (shutdown_tx, shutdown_rx) = mpsc::channel(1);
                        let semaphore = Arc::clone(&task_semaphore);
                        let tx = signal_tx.clone();
                        let symbol_clone = candidate.clone();

                        let task_handle = tokio::spawn(async move {
                            let _permit = semaphore.acquire().await.expect("Semaphore should not be closed");
                            spawn_analysis_task(symbol_clone, tx, shutdown_rx).await;
                        });

                        running_tasks.insert(candidate.clone(), (task_handle, shutdown_tx));
                    }
                }
                info!("[SENTINEL] Sisa kuota task: {}/{}", task_semaphore.available_permits(), max_concurrent_tasks);
            },

            _ = position_monitor_timer.tick() => {
                info!("[SENTINEL] Running periodic position monitoring...");
                tokio::spawn(async {
                    if let Err(e) = call_python_position_monitor() {
                        error!("[SENTINEL] Gagal memanggil position monitor Python: {}. Melanjutkan...", e);
                    }
                });
            },

            Some(signal) = signal_rx.recv() => {
                info!("[SENTINEL] Menerima sinyal: {:?}", signal);
                // Spawn a task to handle the Python execution to avoid blocking the main loop
                let signal_clone = signal.clone();
                tokio::spawn(async move {
                    if let Err(e) = call_python_executor(signal_clone) {
                        error!("[SENTINEL] Gagal memanggil executor Python: {}. Melanjutkan...", e);
                    }
                });
            }
        }
    }
}
