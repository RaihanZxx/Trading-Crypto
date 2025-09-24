//! Data structures for order book and trade data

#![allow(dead_code)]

use crate::config::OFIConfig;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Represents a level in the order book
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookLevel {
    pub price: f64,
    pub quantity: f64,
}

/// Represents the order book for a symbol
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct OrderBookSnapshot {
    pub symbol: String,
    pub bids: Vec<OrderBookLevel>,
    pub asks: Vec<OrderBookLevel>,
    pub timestamp: u64,
}

/// Represents a trade
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")] // Match API response fields
pub struct TradeData {
    pub symbol: String,
    pub price: f64,
    pub quantity: f64,
    pub side: String, // "buy" or "sell"
    pub timestamp: u64,
}

/// In-memory storage for order book data
#[derive(Debug, Clone, Default)]
pub struct OrderBookStorage {
    pub books: HashMap<String, OrderBookSnapshot>,
}

impl OrderBookStorage {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn update_order_book(&mut self, book: OrderBookSnapshot) {
        self.books.insert(book.symbol.clone(), book);
    }

    pub fn get_order_book(&self, symbol: &str) -> Option<&OrderBookSnapshot> {
        self.books.get(symbol)
    }
}

/// In-memory storage for trade data
#[derive(Debug, Clone, Default)]
pub struct TradeStorage {
    pub trades: HashMap<String, Vec<TradeData>>,
}

impl TradeStorage {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn add_trade(&mut self, trade: TradeData, config: &OFIConfig) {
        let entry = self.trades.entry(trade.symbol.clone()).or_default();
        entry.push(trade);
        // Keep only the last N trades to prevent memory leak, using config value
        while entry.len() > config.trade_storage_limit {
            entry.remove(0);
        }
    }

    pub fn get_trades(&self, symbol: &str) -> Option<&Vec<TradeData>> {
        self.trades.get(symbol)
    }

    pub fn get_recent_trades(&self, symbol: &str, limit: usize) -> Vec<&TradeData> {
        self.trades
            .get(symbol)
            .map(|trades| trades.iter().rev().take(limit).collect())
            .unwrap_or_else(Vec::new)
    }
}