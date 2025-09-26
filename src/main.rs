use tokio::sync::{mpsc, Semaphore};
use tokio::time::{interval, Duration};
use std::collections::HashMap;
use std::sync::Arc;
use std::sync::Once;
use pyo3::prelude::*;

// Additional imports for WebSocket functionality and crypto provider
use futures_util::{stream::StreamExt, SinkExt};
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;
use rustls::crypto::ring;

// Import colored crate for modern colored logging
use colored::*;

// Initialize the crypto provider once for the main binary
static INIT: Once = Once::new();


// Structures for deserializing WebSocket messages (these can be moved to mod data.rs if you want)
#[derive(serde::Deserialize, Debug)]
struct BitgetWsResponse {
    arg: BitgetArg,
    data: serde_json::Value,
}
#[derive(serde::Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct BitgetArg {
    channel: String,
    inst_id: String,
}

// Define structs for the actual Bitget WebSocket data format
#[derive(serde::Deserialize, Debug)]
struct BitgetOrderBookData {
    bids: Vec<(String, String)>, // Vektor dari tuple [price_str, quantity_str]
    asks: Vec<(String, String)>,
    ts: String,
}

#[derive(serde::Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct BitgetTradeData {
    ts: String,
    price: String,
    size: String,
    side: String,
}

// Function to call Python Screener
fn call_python_screener() -> PyResult<Vec<String>> {
    Python::with_gil(|py| {
        let screener = PyModule::import_bound(py, "screener.screener")?;
        
        match screener.getattr("get_top_candidates")?.call0() {
            Ok(result) => result.extract(), // Mengembalikan PyResult<Vec<String>>
            Err(e) => {
                // Log Python traceback
                eprintln!("[SENTINEL-ERROR] Panggilan Python ke screener gagal:");
                e.print_and_set_sys_last_vars(py);
                // Kembalikan error yang jelas tanpa membuat Rust panik
                Err(e)
            }
        }
    })
}

// Function to call Python Execution Service
fn call_python_executor(signal: TradingSignal) -> PyResult<()> {
    Python::with_gil(|py| {
        let executor = PyModule::import_bound(py, "execution_service.manager")?;
        let signal_dict = pyo3::types::PyDict::new_bound(py);
        signal_dict.set_item("symbol", &signal.symbol)?;
        signal_dict.set_item("signal_type", &signal.signal_type)?;
        signal_dict.set_item("price", signal.price)?;
        signal_dict.set_item("timestamp", signal.timestamp.to_rfc3339())?;
        
        let result = executor.getattr("handle_trade_signal")?.call1((signal_dict,))?;
        
        // Konversi hasil Python ke Rust
        if let Ok(result_dict) = result.downcast::<pyo3::types::PyDict>() {
            let status_result = result_dict.get_item("status");
            if let Ok(Some(status)) = status_result {
                let status_str: String = status.extract()?;
                if status_str == "error" {
                    let reason_result = result_dict.get_item("reason");
                    let reason = if let Ok(Some(reason_val)) = reason_result {
                        reason_val.extract().unwrap_or_else(|_| "Unknown error".to_string())
                    } else {
                        "Unknown error".to_string()
                    };
                    eprintln!("[SENTINEL-WARN] Eksekusi trade gagal di Python dengan alasan: {}", reason);
                }
            }
        }
        Ok(())
    })
}

// Function to establish WebSocket connection and analyze data for a specific symbol
// This function now uses a persistent WebSocket connection instead of repeatedly connecting and disconnecting

// Import required structures from the library
use ofi_engine_rust::data::{OrderBookLevel, OrderBookSnapshot, TradeData};
use ofi_engine_rust::signals::StrategyParams;
use ofi_engine_rust::engine::OFIEngine;
use ofi_engine_rust::config::OFIConfig;

// Define the TradingSignal structure for the main flow (different from the library's TradingSignal used for internal analysis)
#[derive(Debug, Clone)]
pub struct TradingSignal {
    pub symbol: String,
    pub signal_type: String,  // e.g., "StrongBuy", "StrongSell"
    pub price: f64,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

async fn analyze_symbol_data(
    symbol: String,
    signal_tx: mpsc::Sender<TradingSignal>,
    mut shutdown_rx: mpsc::Receiver<()>
) {
    // 1. Initialize configuration and engine
    let config = match OFIConfig::from_default_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[TASK-ERROR] Gagal memuat config untuk {}: {}", symbol, e);
            return;
        }
    };
    
    let url = match Url::parse(&config.websocket_url) {
        Ok(u) => u,
        Err(e) => {
            eprintln!("[TASK-ERROR] URL WebSocket tidak valid untuk {}: {}", symbol, e);
            return;
        }
    };

    // Create engine instance for this connection (moved outside reconnect loop to preserve state during reconnection)
    let params = StrategyParams {
        imbalance_threshold: config.imbalance_threshold,
        absorption_threshold: config.absorption_threshold,
        delta_threshold: config.delta_threshold,
        lookback_period_ms: config.lookback_period_ms,
        market_condition_multiplier: 1.0, // Default multiplier, will be updated based on market conditions if enabled
    };
    let engine = OFIEngine::new(params, config.clone());

    // Outer reconnect loop - handles reconnection when connection drops
    'reconnect_loop: loop {
        // Wait for shutdown signal before attempting reconnection
        if shutdown_rx.try_recv().is_ok() {
            println!("[TASK] Menerima sinyal shutdown sebelum mencoba rekoneksi untuk {}.", symbol);
            return;
        }

        println!("[TASK] Menghubungkan WebSocket untuk {}...", symbol);
        match connect_async(url.as_str()).await {
            Ok((ws_stream, _)) => {
                println!("[TASK] WebSocket terhubung untuk {}.", symbol);
                let (mut write, mut read) = ws_stream.split();

                // Subscribe to channels
                let sub_msg = serde_json::json!({
                    "op": "subscribe",
                    "args": [
                        { "instType": "USDT-FUTURES", "channel": "books", "instId": &symbol },
                        { "instType": "USDT-FUTURES", "channel": "trade", "instId": &symbol }
                    ]
                });
                if let Err(e) = write.send(Message::Text(sub_msg.to_string().into())).await {
                    eprintln!("[TASK-ERROR] Gagal subscribe untuk {}: {} - mencoba rekoneksi", symbol, e);
                    tokio::time::sleep(Duration::from_secs(5)).await;
                    continue 'reconnect_loop;
                }

                // 2. Inner message processing loop - runs continuously until shutdown or connection error
                
                loop {
                    tokio::select! {
                        // Prioritize shutdown signal
                        _ = shutdown_rx.recv() => {
                            println!("[TASK] Menerima sinyal shutdown untuk {}. Keluar...", symbol);
                            return; // Exit completely
                        },

                        // Process messages from WebSocket
                        Some(msg) = read.next() => {
                            match msg {
                                Ok(Message::Text(text)) => {
                                    if text.contains("\"event\":\"error\"") {
                                        eprintln!("[TASK-ERROR] Received error from exchange: {}", text);
                                        break; // Break and try to reconnect
                                    }
                                    
                                    if text.contains("ping") {
                                        if let Err(e) = write.send(Message::Text("pong".to_string().into())).await {
                                             eprintln!("[TASK-ERROR] Gagal mengirim pong untuk {}: {}", symbol, e);
                                             break; // Break and try to reconnect
                                        }
                                        continue;
                                    }
                                    
                                    // Parse message and update engine
                                    if let Ok(parsed_msg) = serde_json::from_str::<BitgetWsResponse>(&text) {
                                        let channel = &parsed_msg.arg.channel;
                                        let msg_symbol = &parsed_msg.arg.inst_id;
                                        
                                        if channel == "books" {
                                            // Process order book data using serde deserialization
                                            match serde_json::from_value::<Vec<BitgetOrderBookData>>(parsed_msg.data) {
                                                Ok(book_data_vec) => {
                                                    if let Some(book_data) = book_data_vec.first() {
                                                        let parse_level = |level: &(String, String)| -> Result<OrderBookLevel, std::num::ParseFloatError> {
                                                            Ok(OrderBookLevel {
                                                                price: level.0.parse()?,
                                                                quantity: level.1.parse()?,
                                                            })
                                                        };

                                                        let bids: Vec<OrderBookLevel> = book_data.bids.iter().filter_map(|b| parse_level(b).ok()).collect();
                                                        let asks: Vec<OrderBookLevel> = book_data.asks.iter().filter_map(|a| parse_level(a).ok()).collect();

                                                        if !bids.is_empty() && !asks.is_empty() {
                                                            let snapshot = OrderBookSnapshot {
                                                                symbol: msg_symbol.clone(),
                                                                bids,
                                                                asks,
                                                                timestamp: book_data.ts.parse().unwrap_or(0),
                                                            };
                                                            engine.update_order_book(snapshot).await;
                                                            
                                                            // Now picu analisis
                                                            let signal = engine.analyze_symbol(&symbol).await;
                                                            if !matches!(signal.signal_type, ofi_engine_rust::signals::SignalType::NoSignal) {
                                                                println!("[TASK] Signal ditemukan untuk {}: {:?}", symbol, signal.signal_type);
                                                                // ... kirim sinyal
                                                                let new_signal = TradingSignal {
                                                                    symbol: signal.symbol,
                                                                    signal_type: format!("{:?}", signal.signal_type),
                                                                    price: signal.price,
                                                                    timestamp: chrono::Utc::now(),
                                                                };
                                                                if let Err(e) = signal_tx.send(new_signal).await {
                                                                    eprintln!("[TASK] Failed to send signal for {}: {} - shutting down", symbol, e);
                                                                    return; // Channel closed, exit
                                                                }
                                                            }
                                                        }
                                                    }
                                                },
                                                Err(e) => eprintln!("[TASK-ERROR] Gagal mem-parsing data order book untuk {}: {}", msg_symbol, e),
                                            }
                                        } else if channel == "trade" {
                                            // Process trade data using serde deserialization
                                            match serde_json::from_value::<Vec<BitgetTradeData>>(parsed_msg.data) {
                                                Ok(trade_data_vec) => {
                                                    for trade_item in trade_data_vec {
                                                        if let (Ok(price), Ok(quantity), Ok(timestamp)) = (
                                                            trade_item.price.parse(),
                                                            trade_item.size.parse(),
                                                            trade_item.ts.parse()
                                                        ) {
                                                            let trade = TradeData {
                                                                symbol: msg_symbol.clone(),
                                                                price, quantity,
                                                                side: trade_item.side,
                                                                timestamp,
                                                            };
                                                            engine.add_trade(trade).await;
                                                            
                                                            // Now picu analisis
                                                            let signal = engine.analyze_symbol(&symbol).await;
                                                            if !matches!(signal.signal_type, ofi_engine_rust::signals::SignalType::NoSignal) {
                                                                println!("[TASK] Signal ditemukan untuk {}: {:?}", symbol, signal.signal_type);
                                                                // ... kirim sinyal
                                                                let new_signal = TradingSignal {
                                                                    symbol: signal.symbol,
                                                                    signal_type: format!("{:?}", signal.signal_type),
                                                                    price: signal.price,
                                                                    timestamp: chrono::Utc::now(),
                                                                };
                                                                if let Err(e) = signal_tx.send(new_signal).await {
                                                                    eprintln!("[TASK] Failed to send signal for {}: {} - shutting down", symbol, e);
                                                                    return; // Channel closed, exit
                                                                }
                                                            }
                                                        } else {
                                                            eprintln!("[TASK-ERROR] Failed to parse trade data for symbol {}", msg_symbol);
                                                        }
                                                    }
                                                },
                                                Err(e) => eprintln!("[TASK-ERROR] Gagal mem-parsing data trade untuk {}: {}", msg_symbol, e),
                                            }
                                        }
                                    } else {
                                        // If parsing fails but it's not a ping/pong message, log as an error
                                        if !text.contains("pong") && !text.contains("subscribe") {
                                            eprintln!("[TASK-ERROR] Failed to parse WebSocket message: {}", text);
                                        }
                                    }
                                },
                                Ok(_) => { /* Ignore non-text messages */ },
                                Err(e) => {
                                    eprintln!("[TASK-ERROR] Error WebSocket untuk {}: {}. Mencoba rekoneksi...", symbol, e);
                                    break; // Break inner loop and try to reconnect
                                }
                            }
                        }
                    }
                }
            },
            Err(e) => {
                eprintln!("[TASK-ERROR] Gagal menghubungkan WebSocket untuk {}: {}", symbol, e);
            }
        }
        
        // Wait before attempting reconnection
        println!("[TASK] Menunggu 5 detik sebelum mencoba rekoneksi untuk {}...", symbol);
        tokio::time::sleep(Duration::from_secs(5)).await;
    }
}

// Function to spawn an analysis task with semaphore permit (for resource management)
async fn spawn_analysis_task_with_permit(
    symbol: String,
    signal_tx: mpsc::Sender<TradingSignal>,
    shutdown_rx: mpsc::Receiver<()>,
    semaphore: Arc<Semaphore>
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        println!("[TASK] Starting analysis task for {} (with resource permit)", symbol);
        
        // This ensures the permit is held for the entire task duration
        let _permit = semaphore.acquire().await.expect("Semaphore should not be closed");
        analyze_symbol_data(symbol.clone(), signal_tx, shutdown_rx).await;
        
        println!("[TASK] Analysis task for {} terminated", symbol);
        // Permit is automatically released when _permit goes out of scope
    })
}

// Initialize the crypto provider for the binary
fn initialize_crypto_provider() {
    INIT.call_once(|| {
        // Install the Ring crypto provider as the default
        ring::default_provider().install_default().expect("Failed to install crypto provider");
    });
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize crypto provider first
    initialize_crypto_provider();
    
    // Initialize colored logging with modern styling
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format(|buf, record| {
            use std::io::Write;
            
            let timestamp = chrono::Local::now().format("%H:%M:%S");
            let level = record.level();
            
            // Define modern colors for different log levels
            let level_str = match level {
                log::Level::Error => "ERROR".red().bold(),
                log::Level::Warn => "WARN ".yellow().bold(),
                log::Level::Info => "INFO ".green().bold(),
                log::Level::Debug => "DEBUG".blue().bold(),
                log::Level::Trace => "TRACE".cyan().bold(),
            };
            
            let timestamp_str = format!("[{}]", timestamp).bright_black();
            let target_str = format!("{}", record.target()).white();
            
            writeln!(
                buf,
                "{} [{}] [{}] {}",
                timestamp_str,
                level_str,
                target_str,
                record.args()
            )
        })
        .init();
    
    // Load configuration to get max concurrent tasks
    let config = match ofi_engine_rust::config::OFIConfig::from_default_config() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[SENTINEL-ERROR] Gagal memuat konfigurasi: {}", e);
            return Err(e.into());
        }
    };
    
    // Semaphore to limit concurrent tasks (prevent resource exhaustion)
    let max_concurrent_tasks = config.max_concurrent_websocket_connections.unwrap_or(20); // Default to 20
    let task_semaphore = Arc::new(Semaphore::new(max_concurrent_tasks));
    
    // Channel for communication from task analysis to main loop
    let (signal_tx, mut signal_rx) = mpsc::channel(100);
    
    // HashMap to store handles of running tasks and their shutdown senders
    let mut running_tasks: HashMap<String, (tokio::task::JoinHandle<()>, mpsc::Sender<()>)> = HashMap::new();
    
    // Timer for refreshing watchlist every 15 minutes (900 seconds)
    let mut watchlist_refresh_timer = interval(Duration::from_secs(900));
    
    println!("[SENTINEL] OFI Sentinel Dimulai. Menunggu siklus pertama...");
    println!("[SENTINEL] Maksimum koneksi WebSocket simultan: {}", max_concurrent_tasks);
    
    loop {
        tokio::select! {
            // Branch 1: Timer for refreshing watchlist reached
            _ = watchlist_refresh_timer.tick() => {
                println!("[SENTINEL] Waktunya menyegarkan watchlist...");
                
                // Call Python Screener
                let new_candidates = match call_python_screener() {
                    Ok(candidates) => {
                        println!("[SENTINEL] Dapatkan kandidat baru: {:?}", candidates);
                        // Limit the number of candidates to prevent too many tasks
                        let max_candidates = max_concurrent_tasks / 2; // Use at most half of available connections for active analysis
                        if candidates.len() > max_candidates {
                            println!("[SENTINEL] Jumlah kandidat ({}) melebihi batas maksimum ({}), membatasi...", candidates.len(), max_candidates);
                            candidates.into_iter().take(max_candidates).collect()
                        } else {
                            candidates
                        }
                    },
                    Err(e) => {
                        // Jangan `continue`, cukup log error dan lanjutkan dengan watchlist lama
                        eprintln!("[SENTINEL] Gagal mendapatkan kandidat dari Python: {}. Menggunakan watchlist yang ada.", e);
                        // Kembalikan daftar kosong agar tidak ada task baru yang dimulai
                        Vec::new() 
                    }
                };

                // Compare new_candidates with running_tasks
                // Stop tasks for symbols no longer in candidates
                let mut symbols_to_stop = Vec::new();
                for symbol in running_tasks.keys() {
                    if !new_candidates.contains(symbol) {
                        symbols_to_stop.push(symbol.clone());
                    }
                }

                for symbol in symbols_to_stop {
                    println!("[SENTINEL] Menghentikan task untuk simbol: {}", symbol);
                    if let Some((handle, shutdown_tx)) = running_tasks.remove(&symbol) {
                        // 1. Kirim sinyal shutdown. Abaikan error jika channel sudah ditutup.
                        let _ = shutdown_tx.send(()).await;

                        // 2. Tunggu task selesai dengan timeout 5 detik.
                        match tokio::time::timeout(Duration::from_secs(5), handle).await {
                            Ok(_) => {
                                println!("[SENTINEL] Task untuk {} berhasil dihentikan secara graceful.", symbol);
                            }
                            Err(_) => {
                                eprintln!("[SENTINEL-WARN] Task untuk {} gagal berhenti dalam 5 detik. Mungkin hang.", symbol);
                            }
                        }
                    }
                }

                // Start tasks for new candidates not already running
                for candidate in &new_candidates {
                    if !running_tasks.contains_key(candidate) {
                        println!("[SENTINEL] Memulai task baru untuk: {}", candidate);
                        
                        // Create shutdown channel for this task and store the sender
                        let (shutdown_tx, shutdown_rx) = mpsc::channel(1);
                        
                        // Spawn the analysis task with the semaphore
                        let semaphore = Arc::clone(&task_semaphore);
                        let task_handle = spawn_analysis_task_with_permit(
                            candidate.clone(),
                            signal_tx.clone(),
                            shutdown_rx,
                            semaphore
                        ).await;
                        
                        running_tasks.insert(candidate.clone(), (task_handle, shutdown_tx));
                    }
                }
                
                // Log current resource usage
                let available_permits = task_semaphore.available_permits();
                println!("[SENTINEL] Sisa kuota task: {}/{}", available_permits, max_concurrent_tasks);
            },

            // Branch 2: Receive signal from one of the analysis tasks
            Some(signal) = signal_rx.recv() => {
                println!("[SENTINEL] Menerima sinyal: {:?}", signal);
                
                // Call Python Execution Service
                if let Err(e) = call_python_executor(signal) {
                    eprintln!("[SENTINEL] Gagal memanggil executor Python: {}. Melanjutkan...", e);
                }
            }
        }
    }
}