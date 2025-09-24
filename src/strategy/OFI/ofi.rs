//! Order Flow Imbalance (OFI) calculations

#![allow(dead_code)]

use crate::data::{OrderBookSnapshot, TradeData};
use serde::{Deserialize, Serialize};

/// Represents OFI metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OFIMetrics {
    pub symbol: String,
    pub delta: f64,              // Order flow delta (buy volume - sell volume)
    pub cumulative_delta: f64,   // Cumulative order flow delta
    pub buy_imbalance: f64,      // Buy side imbalance ratio
    pub sell_imbalance: f64,     // Sell side imbalance ratio
    pub timestamp: u64,          // Timestamp of calculation
}

/// Calculate OFI metrics
pub fn calculate_ofi_metrics(
    order_book: &OrderBookSnapshot,
    trades: &[&TradeData],
    lookback_period_ms: u64,
) -> OFIMetrics {
    let now = order_book.timestamp;
    let cutoff_time = now.saturating_sub(lookback_period_ms);
    
    // Filter trades within lookback period
    let recent_trades: Vec<&TradeData> = trades
        .iter()
        .filter(|trade| trade.timestamp >= cutoff_time)
        .copied()
        .collect();
    
    // Calculate delta and cumulative delta
    let delta = calculate_delta(&recent_trades);
    let cumulative_delta = calculate_cumulative_delta(&recent_trades);
    
    // Calculate imbalances
    let (buy_imbalance, sell_imbalance) = calculate_imbalances(order_book);
    
    OFIMetrics {
        symbol: order_book.symbol.clone(),
        delta,
        cumulative_delta,
        buy_imbalance,
        sell_imbalance,
        timestamp: now,
    }
}

/// Calculate order flow delta (buy volume - sell volume)
fn calculate_delta(trades: &[&TradeData]) -> f64 {
    let mut buy_volume = 0.0;
    let mut sell_volume = 0.0;
    
    for trade in trades {
        let volume = trade.price * trade.quantity;
        if trade.side == "buy" {
            buy_volume += volume;
        } else if trade.side == "sell" {
            sell_volume += volume;
        }
    }
    
    buy_volume - sell_volume
}

/// Calculate cumulative order flow delta
fn calculate_cumulative_delta(trades: &[&TradeData]) -> f64 {
    let mut cumulative_delta = 0.0;
    
    for trade in trades {
        let volume = trade.price * trade.quantity;
        if trade.side == "buy" {
            cumulative_delta += volume;
        } else if trade.side == "sell" {
            cumulative_delta -= volume;
        }
    }
    
    cumulative_delta
}

/// Calculate buy/sell imbalances from order book
fn calculate_imbalances(order_book: &OrderBookSnapshot) -> (f64, f64) {
    // Calculate total buy side size (bids)
    let total_buy_size: f64 = order_book
        .bids
        .iter()
        .map(|level| level.price * level.quantity)
        .sum();
    
    // Calculate total sell side size (asks)
    let total_sell_size: f64 = order_book
        .asks
        .iter()
        .map(|level| level.price * level.quantity)
        .sum();
    
    // Calculate imbalances as ratios
    let buy_imbalance = if total_sell_size > 0.0 {
        total_buy_size / total_sell_size
    } else {
        0.0
    };
    
    let sell_imbalance = if total_buy_size > 0.0 {
        total_sell_size / total_buy_size
    } else {
        0.0
    };
    
    (buy_imbalance, sell_imbalance)
}

/// Detect stacked imbalances in order book
pub fn detect_stacked_imbalances(order_book: &OrderBookSnapshot, threshold: f64) -> (bool, bool) {
    let buy_stacked = detect_stacked_buy_imbalance(order_book, threshold);
    let sell_stacked = detect_stacked_sell_imbalance(order_book, threshold);
    (buy_stacked, sell_stacked)
}

/// Detect stacked buy imbalances (large bids at top of book) - Improved version
/// Analyzes multiple levels for consistent pressure
fn detect_stacked_buy_imbalance(order_book: &OrderBookSnapshot, threshold: f64) -> bool {
    detect_stacked_buy_imbalance_advanced(order_book, threshold, 5, 3)
}

/// Detect stacked sell imbalances (large asks at top of book) - Improved version
/// Analyzes multiple levels for consistent pressure
fn detect_stacked_sell_imbalance(order_book: &OrderBookSnapshot, threshold: f64) -> bool {
    detect_stacked_sell_imbalance_advanced(order_book, threshold, 5, 3)
}

/// Advanced stacked buy imbalance detection
/// Checks multiple levels to find consistent pressure
fn detect_stacked_buy_imbalance_advanced(
    order_book: &OrderBookSnapshot, 
    threshold: f64, 
    levels_to_check: usize, 
    required_levels: usize
) -> bool {
    if order_book.bids.len() < levels_to_check || order_book.asks.is_empty() {
        return false;
    }

    let top_ask_size = order_book.asks[0].price * order_book.asks[0].quantity;
    if top_ask_size == 0.0 { 
        return false; 
    }

    let mut imbalanced_levels = 0;
    // Check top 5 bid levels
    for i in 0..std::cmp::min(levels_to_check, order_book.bids.len()) {
        let bid_size = order_book.bids[i].price * order_book.bids[i].quantity;
        // Check if bid at this level is significantly larger than top ask
        if (bid_size / top_ask_size) >= threshold {
            imbalanced_levels += 1;
        }
    }

    // Signal valid if at least 3 of 5 levels have imbalance
    imbalanced_levels >= required_levels
}

/// Advanced stacked sell imbalance detection
/// Checks multiple levels to find consistent pressure
fn detect_stacked_sell_imbalance_advanced(
    order_book: &OrderBookSnapshot, 
    threshold: f64, 
    levels_to_check: usize, 
    required_levels: usize
) -> bool {
    if order_book.asks.len() < levels_to_check || order_book.bids.is_empty() {
        return false;
    }

    let top_bid_size = order_book.bids[0].price * order_book.bids[0].quantity;
    if top_bid_size == 0.0 { 
        return false; 
    }

    let mut imbalanced_levels = 0;
    // Check top 5 ask levels
    for i in 0..std::cmp::min(levels_to_check, order_book.asks.len()) {
        let ask_size = order_book.asks[i].price * order_book.asks[i].quantity;
        // Check if ask at this level is significantly larger than top bid
        if (ask_size / top_bid_size) >= threshold {
            imbalanced_levels += 1;
        }
    }

    // Signal valid if at least 3 of 5 levels have imbalance
    imbalanced_levels >= required_levels
}

/// Detect absorption (large trades eating through order book levels)
/// Absorption is when large market volume fails to move price
/// Returns (is_detected, reason_string, signal_type)
pub fn detect_absorption(
    order_book: &OrderBookSnapshot,
    trades: &[&TradeData],
    ofi_metrics: &OFIMetrics,
    params: &crate::signals::StrategyParams,
) -> (bool, String, crate::signals::SignalType) {
    if order_book.bids.is_empty() || trades.is_empty() {
        return (false, String::new(), crate::signals::SignalType::NoSignal);
    }
    
    // Get best bid price
    let best_bid = order_book.bids[0].price;
    
    // Find previous best bid for comparison (if available)
    let prev_best_bid = if order_book.bids.len() > 1 {
        order_book.bids[1].price
    } else {
        best_bid
    };
    
    // Check for Buy Absorption
    // Large negative delta (many sell market orders) but price doesn't drop
    let price_did_not_drop = best_bid >= prev_best_bid;
    
    if ofi_metrics.delta < -params.delta_threshold && price_did_not_drop {
        return (
            true,
            format!("Buy absorption detected: large selling delta ({:.0}) with no price drop.", ofi_metrics.delta),
            crate::signals::SignalType::Buy
        );
    }
    
    // Check for Sell Absorption
    // Large positive delta (many buy market orders) but price doesn't rise
    let price_did_not_rise = best_bid <= prev_best_bid;
    
    if ofi_metrics.delta > params.delta_threshold && price_did_not_rise {
        return (
            true,
            format!("Sell absorption detected: large buying delta ({:.0}) with no price rise.", ofi_metrics.delta),
            crate::signals::SignalType::Sell
        );
    }
    
    (false, String::new(), crate::signals::SignalType::NoSignal)
}