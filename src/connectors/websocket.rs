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
    let url = Url::parse("wss://ws.bitget.com/v2/ws/public")?;
    info!("[Rust] Attempting to connect to WebSocket for {}", symbol);
    let (ws_stream, response) = connect_async(url.to_string()).await.map_err(|e| anyhow!("WebSocket connection failed: {}", e))?;
    info!("[Rust] WebSocket connected for {} with response: {:?}", symbol, response);

    let (mut write, mut read) = ws_stream.split();

    // Subscribe to both order book and trades channels
    let subscription_msg = json!({
        "op": "subscribe",
        "args": [
            { "instType": "USDT-FUTURES", "channel": "books", "instId": symbol },
            { "instType": "USDT-FUTURES", "channel": "trade", "instId": symbol }  // Correct format for trades
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
                                
                                let snapshot = OrderBookSnapshot {
                                    symbol: symbol_from_msg.clone(),
                                    bids: first_book.bids.iter().map(|b| OrderBookLevel {
                                        price: b[0].parse().unwrap_or(0.0),
                                        quantity: b[1].parse().unwrap_or(0.0),
                                    }).collect(),
                                    asks: first_book.asks.iter().map(|a| OrderBookLevel {
                                        price: a[0].parse().unwrap_or(0.0),
                                        quantity: a[1].parse().unwrap_or(0.0),
                                    }).collect(),
                                    timestamp: first_book.ts.parse().unwrap_or(0),
                                };
                                engine.update_order_book(snapshot).await;
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
                                let trade_obj = TradeData {
                                    symbol: symbol_from_msg.clone(),
                                    price: trade.price.parse().unwrap_or(0.0),
                                    quantity: trade.size.parse().unwrap_or(0.0),
                                    side: trade.side.clone(),
                                    timestamp: trade.ts.parse().unwrap_or(0),
                                };
                                engine.add_trade(trade_obj).await;
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