//! WebSocket client for Bitget API

use crate::data::{OrderBookLevel, OrderBookSnapshot, TradeData};
use crate::engine::OFIEngine;
use crate::signals::{SignalType, TradingSignal};
use anyhow::{anyhow, Result};
use futures_util::{stream::StreamExt, SinkExt};
use log::{error, info, warn};
use serde::Deserialize;
use serde_json::json;
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use url::Url;

// --- Structs for Deserializing Bitget WebSocket Messages ---

#[derive(Deserialize, Debug)]
struct BitgetWsResponse {
    #[allow(dead_code)]
    action: Option<String>,
    arg: BitgetArg,
    data: serde_json::Value,
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
    // checksum: u32, // We don't use checksum for now
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
struct BitgetTradeData {
    ts: String,
    price: String,
    size: String,
    side: String,
}

// --- Main WebSocket Connection and Listener ---

pub async fn connect_and_listen(
    symbol: &str,
    engine: OFIEngine,
) -> Result<TradingSignal> {
    // Validate input parameters
    if symbol.is_empty() || symbol.len() > 20 {
        return Err(anyhow!("Invalid symbol: must be between 1-20 characters"));
    }
    
    // Get the WebSocket URL from the engine's configuration
    let config = engine.config();
    let url = Url::parse(&config.websocket_url)?;
    info!("[Rust] Attempting to connect to WebSocket for {} at {}", symbol, config.websocket_url);
    let (ws_stream, response) = connect_async(url.to_string()).await.map_err(|e| anyhow!("WebSocket connection failed: {}", e))?;
    info!("[Rust] WebSocket connected for {} with response: {:?}", symbol, response);

    let (mut write, mut read) = ws_stream.split();

    // Subscribe to both order book and trades channels
    let subscription_msg = json!({
        "op": "subscribe",
        "args": [
            { "instType": "USDT-FUTURES", "channel": "books", "instId": symbol },
            { "instType": "USDT-FUTURES", "channel": "trade", "instId": symbol }
        ]
    });

    info!("[Rust] Sending subscription message: {}", subscription_msg.to_string());
    write.send(Message::Text(subscription_msg.to_string().into())).await?;
    info!("[Rust] Subscribed to order book and trade channels for {}", symbol);

    // --- Main Message Processing Loop ---
    let mut message_count = 0;
    while let Some(msg) = read.next().await {
        message_count += 1;
        let msg = match msg {
            Ok(msg) => msg,
            Err(e) => {
                error!("[Rust] Error reading from WebSocket: {}", e);
                continue;
            }
        };

        if let Message::Text(text) = msg {
            info!("[Rust] Received message #{}: {}", message_count, &text[..std::cmp::min(text.len(), 200)]); // Log first 200 chars
            
            if text.contains("\"event\":\"error\"") {
                warn!("[Rust] Received error from Bitget: {}", text);
                continue;
            }

            // Attempt to parse the message
            let parsed_msg: Result<BitgetWsResponse, _> = serde_json::from_str(&text);

            match parsed_msg {
                Ok(response) => {
                    let channel = &response.arg.channel;
                    let symbol_from_msg = &response.arg.inst_id;
                    info!("[Rust] Parsed message for channel '{}' and symbol '{}'", channel, symbol_from_msg);

                    // --- Handle Order Book Updates ---
                    if channel == "books" {
                        let book_data: Result<Vec<BitgetOrderBookData>, _> = serde_json::from_value(response.data);
                        if let Ok(data) = book_data {
                            if let Some(first_book) = data.first() {
                                info!("[Rust] Received order book update for {}: {} bids, {} asks", 
                                    symbol_from_msg, first_book.bids.len(), first_book.asks.len());
                                
                                let bids: Result<Vec<OrderBookLevel>, anyhow::Error> = first_book.bids.iter().map(|b| {
                                    let price = b[0].parse::<f64>().map_err(|e| anyhow::anyhow!("Invalid price format: {}", e))?;
                                    let quantity = b[1].parse::<f64>().map_err(|e| anyhow::anyhow!("Invalid quantity format: {}", e))?;
                                    Ok(OrderBookLevel { price, quantity })
                                }).collect();
                                
                                let asks: Result<Vec<OrderBookLevel>, anyhow::Error> = first_book.asks.iter().map(|a| {
                                    let price = a[0].parse::<f64>().map_err(|e| anyhow::anyhow!("Invalid price format: {}", e))?;
                                    let quantity = a[1].parse::<f64>().map_err(|e| anyhow::anyhow!("Invalid quantity format: {}", e))?;
                                    Ok(OrderBookLevel { price, quantity })
                                }).collect();
                                
                                if let (Ok(bids), Ok(asks)) = (bids, asks) {
                                    let snapshot = OrderBookSnapshot {
                                        symbol: symbol_from_msg.clone(),
                                        bids,
                                        asks,
                                        timestamp: first_book.ts.parse().unwrap_or(0),
                                    };
                                    engine.update_order_book(snapshot).await;
                                } else {
                                    error!("[Rust] Failed to parse order book prices/quantities for symbol {}", symbol_from_msg);
                                }
                            }
                        } else {
                            error!("[Rust] Failed to parse book data: {:?}", book_data);
                        }
                    }
                    // --- Handle Trade Updates ---
                    else if channel == "trade" {
                        let trade_data: Result<Vec<BitgetTradeData>, _> = serde_json::from_value(response.data);
                        if let Ok(data) = trade_data {
                            info!("[Rust] Received {} trade updates for {}", data.len(), symbol_from_msg);
                            for trade in data {
                                if let (Ok(price), Ok(quantity), Ok(timestamp)) = (
                                    trade.price.parse::<f64>(),
                                    trade.size.parse::<f64>(),
                                    trade.ts.parse::<u64>()
                                ) {
                                    let trade_obj = TradeData {
                                        symbol: symbol_from_msg.clone(),
                                        price,
                                        quantity,
                                        side: trade.side.clone(),
                                        timestamp,
                                    };
                                    engine.add_trade(trade_obj).await;
                                } else {
                                    error!("[Rust] Failed to parse trade data for symbol {}: price={}, size={}, ts={}", 
                                           symbol_from_msg, trade.price, trade.size, trade.ts);
                                }
                            }
                        } else {
                            error!("[Rust] Failed to parse trade data: {:?}", trade_data);
                        }
                    }

                    // --- Analyze for signals after every message ---
                    let signal = engine.analyze_symbol(symbol).await;
                    if !matches!(signal.signal_type, SignalType::NoSignal) {
                        info!("[Rust] Signal found for {}: {:?}", symbol, signal.signal_type);
                        return Ok(signal); // Return immediately upon finding a signal
                    }
                }
                Err(e) => {
                    // Ignore ping/pong or other non-JSON messages
                    if !text.contains("ping") {
                        error!("[Rust] Failed to parse WebSocket message: {}. Raw: {}", e, &text[..std::cmp::min(text.len(), 200)]);
                    }
                }
            }
        }
        
        // Limit the number of messages for testing
        if message_count > 50 {
            info!("[Rust] Reached message limit for testing, stopping...");
            break;
        }
    }

    // This part is reached if the WebSocket stream closes unexpectedly.
    warn!("[Rust] WebSocket stream for {} ended.", symbol);
    Ok(TradingSignal::no_signal(symbol)) // Return a NoSignal if the loop exits
}