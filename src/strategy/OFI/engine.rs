//! Main OFI analysis engine

#![allow(dead_code)]

use crate::data::{OrderBookSnapshot, OrderBookStorage, TradeData, TradeStorage};
use crate::signals::{detect_signals, StrategyParams, TradingSignal};
use crate::websocket::connect_and_listen;
use anyhow::Result;
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
}

impl OFIEngine {
    /// Create a new OFI engine with specific strategy parameters
    pub fn new(params: StrategyParams) -> Self {
        Self {
            order_book_storage: Arc::new(Mutex::new(OrderBookStorage::new())),
            trade_storage: Arc::new(Mutex::new(TradeStorage::new())),
            strategy_params: params,
        }
    }

    /// Update order book data
    pub async fn update_order_book(&self, book: OrderBookSnapshot) {
        let mut storage = self.order_book_storage.lock().await;
        storage.update_order_book(book);
    }

    /// Add trade data
    pub async fn add_trade(&self, trade: TradeData) {
        let mut storage = self.trade_storage.lock().await;
        storage.add_trade(trade);
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
        detect_signals(&order_book, &recent_trades, &self.strategy_params)
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
    info!("[Rust] Starting analysis for {} for {}ms", symbol, duration_ms);

    // 1. Create strategy parameters from Python input
    let params = StrategyParams {
        imbalance_threshold: imbalance_ratio,
        delta_threshold,
        lookback_period_ms,
        ..Default::default()
    };

    // 2. Create a new engine instance for this specific analysis run
    let engine = OFIEngine::new(params);
    let analysis_duration = Duration::from_millis(duration_ms);

    // 3. Run the WebSocket listener within a timeout
    match timeout(analysis_duration, connect_and_listen(&symbol, engine)).await {
        Ok(Ok(final_signal)) => {
            // The listener returned a signal within the time limit.
            // Check if it's a real signal or a NoSignal from a clean exit.
            if matches!(final_signal.signal_type, crate::signals::SignalType::NoSignal) {
                info!("[Rust] Analysis complete for {}. No significant signal found.", symbol);
                Ok(None)
            } else {
                info!("[Rust] Analysis complete for {}. Signal found: {:?}", symbol, final_signal.signal_type);
                Ok(Some(final_signal))
            }
        }
        Ok(Err(e)) => {
            // The listener function itself returned an error (e.g., connection failed)
            error!("[Rust] Error during WebSocket analysis for {}: {}", symbol, e);
            Err(e)
        }
        Err(_) => {
            // The analysis timed out
            info!("[Rust] Analysis for {} timed out after {}ms. No signal generated.", symbol, duration_ms);
            Ok(None) // It's not an error to time out, it just means no signal was found
        }
    }
}