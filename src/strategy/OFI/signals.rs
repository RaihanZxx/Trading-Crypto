//! Signal detection based on OFI strategy

#![allow(dead_code)]

use crate::data::{OrderBookSnapshot, TradeData};
use crate::ofi::{calculate_ofi_metrics, detect_absorption, detect_stacked_imbalances};
use serde::{Deserialize, Serialize};

/// Represents a trading signal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SignalType {
    StrongBuy,
    StrongSell,
    Buy,
    Sell,
    NoSignal,
}

/// Trading signal with details
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradingSignal {
    pub symbol: String,
    pub signal_type: SignalType,
    pub price: f64,
    pub confidence: f64, // 0.0 to 1.0
    pub reason: String,
    pub timestamp: u64,
}

impl TradingSignal {
    /// Helper to create a default NoSignal instance
    pub fn no_signal(symbol: &str) -> Self {
        Self {
            symbol: symbol.to_string(),
            signal_type: SignalType::NoSignal,
            price: 0.0,
            confidence: 0.0,
            reason: "No significant signal detected".to_string(),
            timestamp: 0,
        }
    }
    
    /// Helper to create a NoSignal with a specific reason
    pub fn no_signal_with_reason(symbol: &str, reason: &str) -> Self {
        Self {
            symbol: symbol.to_string(),
            signal_type: SignalType::NoSignal,
            price: 0.0,
            confidence: 0.0,
            reason: reason.to_string(),
            timestamp: 0,
        }
    }
}

/// Strategy parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyParams {
    pub imbalance_threshold: f64,     // Threshold for detecting imbalances
    pub absorption_threshold: f64,    // Threshold for detecting absorption
    pub delta_threshold: f64,         // Threshold for delta significance
    pub lookback_period_ms: u64,      // Lookback period in milliseconds
    pub market_condition_multiplier: f64, // Multiplier based on market conditions
}

/// Detect trading signals based on OFI analysis
pub fn detect_signals(
    order_book: &OrderBookSnapshot,
    trades: &[&TradeData],
    params: &StrategyParams,
    strong_signal_confidence: f64,
    reversal_signal_confidence: f64,
    exhaustion_signal_confidence: f64,
) -> TradingSignal {
    // Calculate OFI metrics
    let ofi_metrics = calculate_ofi_metrics(order_book, trades, params.lookback_period_ms);
    
    // Get current price (mid price)
    let best_bid = order_book.bids.first().map(|b| b.price).unwrap_or(0.0);
    let best_ask = order_book.asks.first().map(|a| a.price).unwrap_or(0.0);
    let current_price = if best_bid > 0.0 && best_ask > 0.0 {
        (best_bid + best_ask) / 2.0
    } else {
        best_bid.max(best_ask)
    };
    
    // Adjust parameters based on market condition multiplier
    let adjusted_imbalance_threshold = params.imbalance_threshold * params.market_condition_multiplier;
    let adjusted_delta_threshold = params.delta_threshold * params.market_condition_multiplier;
    
    // Detect stacked imbalances with adjusted threshold
    let (buy_stacked, sell_stacked) = detect_stacked_imbalances(order_book, adjusted_imbalance_threshold);
    
    // Create a copy of params with adjusted values
    let adjusted_params = crate::signals::StrategyParams {
        imbalance_threshold: adjusted_imbalance_threshold,
        absorption_threshold: params.absorption_threshold * params.market_condition_multiplier,
        delta_threshold: adjusted_delta_threshold,
        lookback_period_ms: params.lookback_period_ms,
        market_condition_multiplier: params.market_condition_multiplier,
    };
    
    // Detect absorption - using improved logic from ofi.rs with adjusted params
    let absorption_detected = detect_absorption(order_book, trades, &ofi_metrics, &adjusted_params);
    
    // Determine signal based on strategy rules using adjusted parameters
    
    // 1. Continuation signals
    if buy_stacked && ofi_metrics.delta > adjusted_delta_threshold {
        // Strong buy signal - stacked buy imbalances with positive delta
        return TradingSignal {
            symbol: order_book.symbol.clone(),
            signal_type: SignalType::StrongBuy,
            price: current_price,
            confidence: strong_signal_confidence,
            reason: format!("Stacked buy imbalances with strong positive delta (adjusted threshold: {:.2})", adjusted_delta_threshold),
            timestamp: ofi_metrics.timestamp,
        };
    }
    
    if sell_stacked && ofi_metrics.delta < -adjusted_delta_threshold {
        // Strong sell signal - stacked sell imbalances with negative delta
        return TradingSignal {
            symbol: order_book.symbol.clone(),
            signal_type: SignalType::StrongSell,
            price: current_price,
            confidence: strong_signal_confidence,
            reason: format!("Stacked sell imbalances with strong negative delta (adjusted threshold: {:.2})", adjusted_delta_threshold),
            timestamp: ofi_metrics.timestamp,
        };
    }
    
    // 2. Reversal signals using improved absorption detection
    if absorption_detected.0 {
        // Buy/Sell signal - absorption detected
        return TradingSignal {
            symbol: order_book.symbol.clone(),
            signal_type: absorption_detected.2, // Use the signal type from absorption detection
            price: current_price,
            confidence: reversal_signal_confidence,
            reason: absorption_detected.1, // Use the reason from absorption detection
            timestamp: ofi_metrics.timestamp,
        };
    }
    
    // 3. Check for exhaustion (delta turning negative after strong positive)
    if ofi_metrics.delta < -adjusted_delta_threshold && ofi_metrics.cumulative_delta > adjusted_delta_threshold * 2.0 {
        // Sell signal - exhaustion
        return TradingSignal {
            symbol: order_book.symbol.clone(),
            signal_type: SignalType::Sell,
            price: current_price,
            confidence: exhaustion_signal_confidence,
            reason: format!("Potential exhaustion detected (adjusted threshold: {:.2})", adjusted_delta_threshold),
            timestamp: ofi_metrics.timestamp,
        };
    }
    
    // No strong signal detected
    TradingSignal {
        symbol: order_book.symbol.clone(),
        signal_type: SignalType::NoSignal,
        price: current_price,
        confidence: 0.0,
        reason: "No significant signal detected".to_string(),
        timestamp: ofi_metrics.timestamp,
    }
}

