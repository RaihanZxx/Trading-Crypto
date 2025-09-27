//! WebSocket client for Bitget API

use crate::data::{OrderBookLevel, OrderBookSnapshot, TradeData};
use crate::engine::OFIEngine;
use crate::signals::{SignalType, TradingSignal};
use anyhow::{anyhow, Result};
use futures_util::{stream::StreamExt, SinkExt};
use log::{error, info, warn};
use serde::Deserialize;
use serde_json::json;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;

// --- Structs for Deserializing Bitget WebSocket Messages ---

#[derive(Deserialize, Debug)]
struct BitgetWsResponse {
    #[allow(dead_code)]
    action: Option<String>,
    arg: BitgetArg,
    data: Option<serde_json::Value>,
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct BitgetArg {
    #[allow(dead_code)]
    inst_type: String,
    channel: String,
    inst_id: String,
}

#[derive(Deserialize, Debug)]
struct BitgetOrderBookData {
    bids: Vec<[String; 2]>,
    asks: Vec<[String; 2]>,
    ts: String,
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct BitgetTradeData {
    ts: String,
    price: String,
    size: String,
    side: String,
}

// --- WebSocket Connection Manager ---

/// Manages the WebSocket connection, handling automatic reconnections.
///
/// This function will run indefinitely, attempting to reconnect on any disconnection.
/// It returns a receiver channel from which trading signals can be consumed.
pub async fn run_websocket_manager(
    symbol: String,
    engine: OFIEngine,
) -> mpsc::Receiver<TradingSignal> {
    let (tx, rx) = mpsc::channel(100); // Channel for trading signals

    tokio::spawn(async move {
        loop {
            info!("[Rust] Attempting to establish WebSocket connection for {}...", symbol);
            let connection_result =
                connect_and_listen(&symbol, engine.clone(), tx.clone()).await;

            match connection_result {
                Ok(_) => {
                    warn!("[Rust] WebSocket for {} disconnected cleanly. Reconnecting in 5 seconds...", symbol);
                }
                Err(e) => {
                    error!("[Rust] WebSocket for {} disconnected with error: {}. Reconnecting in 5 seconds...", symbol, e);
                }
            }
            // Wait before attempting to reconnect
            tokio::time::sleep(Duration::from_secs(5)).await;
        }
    });

    rx
}

/// Connects to the WebSocket, subscribes to channels, and listens for messages.
///
/// This function will exit upon any disconnection or critical error, leaving the
/// reconnection logic to the `run_websocket_manager`.
async fn connect_and_listen(
    symbol: &str,
    engine: OFIEngine,
    signal_tx: mpsc::Sender<TradingSignal>,
) -> Result<()> {
    if symbol.is_empty() || symbol.len() > 20 {
        return Err(anyhow!("Invalid symbol: must be between 1-20 characters"));
    }

    let config = engine.config();
    let url = Url::parse(&config.websocket_url)?;
    let (ws_stream, response) = connect_async(url.to_string())
        .await
        .map_err(|e| anyhow!("WebSocket connection failed: {}", e))?;
    info!("[Rust] WebSocket connected for {} with response: {:?}", symbol, response.status());

    let (mut write, mut read) = ws_stream.split();

    let subscription_msg = json!({
        "op": "subscribe",
        "args": [
            { "instType": "USDT-FUTURES", "channel": "books", "instId": symbol },
            { "instType": "USDT-FUTURES", "channel": "trade", "instId": symbol }
        ]
    });

    write.send(Message::Text(subscription_msg.to_string().into())).await?;
    info!("[Rust] Subscribed to order book and trade channels for {}", symbol);

    let mut ping_interval = tokio::time::interval(Duration::from_secs(25));
    let mut last_message_time = tokio::time::Instant::now();

    loop {
        tokio::select! {
            // Send a ping at a regular interval to keep the connection alive
            _ = ping_interval.tick() => {
                info!("[Rust] Sending Ping to server.");
                if write.send(Message::Ping(Vec::new().into())).await.is_err() {
                    error!("[Rust] Failed to send ping. Connection likely closed.");
                    break; // Exit to trigger reconnection
                }
            }

            // Process incoming messages from the WebSocket
            msg = read.next() => {
                match msg {
                    Some(Ok(message)) => {
                        last_message_time = tokio::time::Instant::now(); // Reset timer on any message
                        handle_message(message, symbol, &engine, &signal_tx).await?;
                    }
                    Some(Err(e)) => {
                        error!("[Rust] Error reading from WebSocket: {}", e);
                        break; // Exit to trigger reconnection
                    }
                    None => {
                        warn!("[Rust] WebSocket stream for {} ended.", symbol);
                        break; // Exit to trigger reconnection
                    }
                }
            }
        }
        // Check for connection timeout (no messages received for a long time)
        if last_message_time.elapsed() > Duration::from_secs(120) {
            warn!("[Rust] WebSocket timeout for {}: No message received in 120 seconds.", symbol);
            break; // Exit to trigger reconnection
        }
    }

    Ok(())
}

/// Handles a single WebSocket message.
async fn handle_message(
    msg: Message,
    symbol: &str,
    engine: &OFIEngine,
    signal_tx: &mpsc::Sender<TradingSignal>,
) -> Result<()> {
    match msg {
        Message::Text(text) => {
            if text.contains("pong") {
                info!("[Rust] Received Pong from server.");
                return Ok(());
            }
            if text.contains("\"event\":\"error\"") {
                warn!("[Rust] Received error from Bitget: {}", text);
                return Ok(());
            }

            let parsed_msg: Result<BitgetWsResponse, _> = serde_json::from_str(&text);
            match parsed_msg {
                Ok(response) => {
                    if let Some(data) = response.data {
                        let channel = &response.arg.channel;
                        let symbol_from_msg = &response.arg.inst_id;

                        if channel == "books" {
                            parse_and_update_orderbook(data, symbol_from_msg, engine).await;
                        } else if channel == "trade" {
                            parse_and_update_trades(data, symbol_from_msg, engine).await;
                        }

                        // --- Analyze for signals after every message ---
                        let signal = engine.analyze_symbol(symbol).await;
                        if !matches!(signal.signal_type, SignalType::NoSignal) {
                            info!("[Rust] Signal found for {}: {:?}. Sending to handler.", symbol, signal.signal_type);
                            if signal_tx.send(signal).await.is_err() {
                                error!("[Rust] Failed to send signal: receiver has been dropped.");
                                return Err(anyhow!("Signal channel closed"));
                            }
                        }
                    }
                }
                Err(e) => {
                    error!("[Rust] Failed to parse WebSocket message: {}. Raw: {}", e, &text[..std::cmp::min(text.len(), 200)]);
                }
            }
        }
        Message::Ping(_ping_data) => {
            info!("[Rust] Received Ping from server, sending Pong back.");
        }
        Message::Pong(_) => {
            info!("[Rust] Received Pong from server.");
        }
        Message::Close(close_frame) => {
            warn!("[Rust] Received Close frame: {:?}", close_frame);
            return Err(anyhow!("Connection closed by server"));
        }
        Message::Binary(_) => {
            info!("[Rust] Received binary data (unhandled).");
        }
        Message::Frame(_) => {
            // Low-level frames can be ignored for our application logic.
            info!("[Rust] Received a WebSocket frame (unhandled).");
        }
    }
    Ok(())
}

async fn parse_and_update_orderbook(data: serde_json::Value, symbol: &str, engine: &OFIEngine) {
    let book_data: Result<Vec<BitgetOrderBookData>, _> = serde_json::from_value(data);
    if let Ok(data) = book_data {
        if let Some(first_book) = data.first() {
            let bids_result: Result<Vec<OrderBookLevel>, _> = first_book.bids.iter().map(|b| {
                b[0].parse().and_then(|price| b[1].parse().map(|quantity| OrderBookLevel { price, quantity }))
            }).collect();
            let asks_result: Result<Vec<OrderBookLevel>, _> = first_book.asks.iter().map(|a| {
                a[0].parse().and_then(|price| a[1].parse().map(|quantity| OrderBookLevel { price, quantity }))
            }).collect();

            let timestamp = match first_book.ts.parse::<u64>() {
                Ok(ts) => ts,
                Err(e) => {
                    error!("[Rust] Failed to parse order book timestamp '{}': {}. Skipping update.", first_book.ts, e);
                    return;
                }
            };

            if let (Ok(bids), Ok(asks)) = (bids_result, asks_result) {
                let snapshot = OrderBookSnapshot { symbol: symbol.to_string(), bids, asks, timestamp };
                engine.update_order_book(snapshot).await;
            } else {
                error!("[Rust] Failed to parse order book prices/quantities for symbol {}", symbol);
            }
        }
    } else {
        error!("[Rust] Failed to deserialize order book data for symbol {}", symbol);
    }
}

async fn parse_and_update_trades(data: serde_json::Value, symbol: &str, engine: &OFIEngine) {
    let trade_data: Result<Vec<BitgetTradeData>, _> = serde_json::from_value(data);
    if let Ok(data) = trade_data {
        for trade in data {
            if let (Ok(price), Ok(quantity), Ok(timestamp)) = (trade.price.parse(), trade.size.parse(), trade.ts.parse()) {
                let trade_obj = TradeData { symbol: symbol.to_string(), price, quantity, side: trade.side.clone(), timestamp };
                engine.add_trade(trade_obj).await;
            } else {
                error!("[Rust] Failed to parse trade data for symbol {}: price={}, size={}, ts={}", symbol, trade.price, trade.size, trade.ts);
            }
        }
    } else {
        error!("[Rust] Failed to deserialize trade data for symbol {}", symbol);
    }
}