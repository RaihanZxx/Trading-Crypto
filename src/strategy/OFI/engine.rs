//! Main OFI analysis engine

#![allow(dead_code)]

use crate::config::OFIConfig;
use crate::data::{OrderBookSnapshot, OrderBookStorage, TradeData, TradeStorage};
use crate::signals::{detect_signals, StrategyParams, TradingSignal};
use crate::websocket::run_websocket_manager;
use anyhow::{anyhow, Result};
use log::{error, info};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;
use tokio::time::timeout;

/// OFI Analysis Engine - acts as a state manager
#[derive(Clone)]
pub struct OFIEngine {
    order_book_storage: Arc<Mutex<OrderBookStorage>>,
    trade_storage: Arc<Mutex<TradeStorage>>,
    strategy_params: StrategyParams,
    config: OFIConfig,
}

impl OFIEngine {
    /// Create a new OFI engine with specific strategy parameters and configuration
    pub fn new(params: StrategyParams, config: OFIConfig) -> Self {
        Self {
            order_book_storage: Arc::new(Mutex::new(OrderBookStorage::new())),
            trade_storage: Arc::new(Mutex::new(TradeStorage::new())),
            strategy_params: params,
            config,
        }
    }

    /// Get reference to the configuration
    pub fn config(&self) -> &OFIConfig {
        &self.config
    }

    /// Update order book data
    pub async fn update_order_book(&self, book: OrderBookSnapshot) {
        let mut storage = self.order_book_storage.lock().await;
        storage.update_order_book(book);
    }

    /// Add trade data
    pub async fn add_trade(&self, trade: TradeData) {
        let mut storage = self.trade_storage.lock().await;
        storage.add_trade(trade, &self.config);
    }

    /// Analyze a symbol for trading signals based on current stored data
    pub async fn analyze_symbol(&self, symbol: &str) -> TradingSignal {
        let order_book_storage = self.order_book_storage.lock().await;
        let trade_storage = self.trade_storage.lock().await;

        let order_book = match order_book_storage.get_order_book(symbol) {
            Some(book) => book.clone(),
            None => return TradingSignal::no_signal_with_reason(symbol, "No order book data"),
        };
        
        // Ensure book is not empty
        if order_book.bids.is_empty() || order_book.asks.is_empty() {
             return TradingSignal::no_signal_with_reason(symbol, "Order book is empty");
        }

        let recent_trades = trade_storage.get_recent_trades(symbol, 100);

        // Detect signals
        detect_signals(
            &order_book, 
            &recent_trades, 
            &self.strategy_params,
            self.config.strong_signal_confidence,
            self.config.reversal_signal_confidence,
            self.config.exhaustion_signal_confidence
        )
    }
}

// Helper function to run analysis with a specific configuration (used by Python bindings)
pub async fn run_analysis_with_config(
    symbol: String,
    imbalance_ratio: f64,
    duration_ms: u64,
    delta_threshold: f64,
    lookback_period_ms: u64,
    config: crate::config::OFIConfig,
) -> Result<Option<TradingSignal>> {
    // Input validation
    if symbol.is_empty() { return Err(anyhow!("Symbol cannot be empty")); }
    if symbol.len() > 20 { return Err(anyhow!("Symbol is too long: max 20 characters")); }
    if !symbol.chars().all(|c| c.is_alphanumeric() || c == '_' || c == '-' || c == '/') {
        return Err(anyhow!("Symbol contains invalid characters"));
    }
    if imbalance_ratio <= 0.0 { return Err(anyhow!("Imbalance ratio must be positive")); }
    if duration_ms == 0 || duration_ms > config.analysis_duration_limit_ms {
        return Err(anyhow!("Duration must be between 1ms and {}ms", config.analysis_duration_limit_ms));
    }
    if delta_threshold <= 0.0 { return Err(anyhow!("Delta threshold must be positive")); }
    if lookback_period_ms == 0 || lookback_period_ms > 300000 { // 5 minutes max
        return Err(anyhow!("Lookback period must be between 1ms and 5 minutes"));
    }

    info!("[Rust] Starting analysis for {} for {}ms", symbol, duration_ms);

    let params = crate::signals::StrategyParams {
        imbalance_threshold: imbalance_ratio,
        absorption_threshold: config.absorption_threshold,
        delta_threshold,
        lookback_period_ms,
        market_condition_multiplier: 1.0,
    };

    let engine = OFIEngine::new(params, config);
    let analysis_duration = Duration::from_millis(duration_ms);

    // Run the WebSocket manager and wait for the first signal within a timeout
    let mut signal_rx = run_websocket_manager(symbol.clone(), engine).await;

    match timeout(analysis_duration, signal_rx.recv()).await {
        Ok(Some(signal)) => {
            // A signal was received within the time limit.
            if matches!(signal.signal_type, crate::signals::SignalType::NoSignal) {
                info!("[Rust] Analysis complete for {}. No significant signal found.", symbol);
                Ok(None)
            } else {
                info!("[Rust] Analysis complete for {}. Signal found: {:?}", symbol, signal.signal_type);
                Ok(Some(signal))
            }
        }
        Ok(None) => {
            // The channel was closed without sending a signal.
            error!("[Rust] WebSocket manager for {} shut down unexpectedly.", symbol);
            Err(anyhow!("WebSocket manager shutdown"))
        }
        Err(_) => {
            // The recv() operation timed out.
            info!("[Rust] Analysis for {} timed out after {}ms. No signal generated.", symbol, duration_ms);
            Ok(None) // It's not an error to time out.
        }
    }
}

// This is the core async function that will be called by our Python bridge
pub async fn run_analysis(
    symbol: String,
    imbalance_ratio: f64,
    duration_ms: u64,
    delta_threshold: f64,
    lookback_period_ms: u64,
) -> Result<Option<TradingSignal>> {
    // Load configuration
    let config = match OFIConfig::from_default_config() {
        Ok(config) => config,
        Err(e) => {
            error!("[Rust] Failed to load configuration: {}", e);
            return Err(anyhow!("Configuration error: {}", e));
        }
    };

    // Delegate to the detailed implementation
    run_analysis_with_config(
        symbol,
        imbalance_ratio,
        duration_ms,
        delta_threshold,
        lookback_period_ms,
        config,
    ).await
}