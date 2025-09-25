// src/utils/lib.rs

#[path = "../config/mod.rs"]
pub mod config;

#[path = "../strategy/OFI/data.rs"]
pub mod data;

#[path = "../strategy/OFI/engine.rs"]
pub mod engine;

#[path = "../strategy/OFI/ofi.rs"]
mod ofi;

#[path = "../strategy/OFI/signals.rs"]
pub mod signals;

#[path = "../connectors/websocket.rs"]
mod websocket;

use crate::config::OFIConfig;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rustls::crypto::ring;
use std::collections::HashMap;
use std::sync::Once;
use tokio;

// Initialize the crypto provider once
static INIT: Once = Once::new();

fn initialize_crypto_provider() {
    INIT.call_once(|| {
        // Install the Ring crypto provider as the default
        ring::default_provider().install_default().expect("Failed to install crypto provider");
    });
}

// Re-export the internal TradingSignal for Python
#[pyclass]
pub struct TradingSignal {
    #[pyo3(get, set)]
    pub symbol: String,
    #[pyo3(get, set)]
    pub signal_type: String,
    #[pyo3(get, set)]
    pub price: f64,
    #[pyo3(get, set)]
    pub confidence: f64,
    #[pyo3(get, set)]
    pub timestamp: String,
    #[pyo3(get, set)]
    pub reason: String,
}

#[pymethods]
impl TradingSignal {
    #[new]
    fn new(symbol: String, signal_type: String, price: f64, confidence: f64, timestamp: String, reason: String) -> Self {
        TradingSignal {
            symbol,
            signal_type,
            price,
            confidence,
            timestamp,
            reason,
        }
    }
    
    fn __repr__(&self) -> PyResult<String> {
        Ok(format!(
            "TradingSignal(symbol='{}', signal_type='{}', price={}, confidence={}, timestamp='{}', reason='{}')",
            self.symbol, self.signal_type, self.price, self.confidence, self.timestamp, self.reason
        ))
    }
    
    fn to_dict(&self, py: Python) -> PyResult<PyObject> {
        let dict = PyDict::new_bound(py);
        dict.set_item("symbol", &self.symbol)?;
        dict.set_item("signal_type", &self.signal_type)?;
        dict.set_item("price", self.price)?;
        dict.set_item("confidence", self.confidence)?;
        dict.set_item("timestamp", &self.timestamp)?;
        dict.set_item("reason", &self.reason)?;
        Ok(dict.into())
    }
}

// Convert internal TradingSignal to Python TradingSignal
impl From<signals::TradingSignal> for TradingSignal {
    fn from(signal: signals::TradingSignal) -> Self {
        TradingSignal {
            symbol: signal.symbol,
            signal_type: format!("{:?}", signal.signal_type),
            price: signal.price,
            confidence: signal.confidence,
            timestamp: signal.timestamp.to_string(),
            reason: signal.reason,
        }
    }
}

/// Main OFI analysis engine
#[pyclass]
pub struct OFIEngine {
    config: OFIConfig,
}

#[pymethods]
impl OFIEngine {
    #[new]
    fn new(api_key: String, secret_key: String, passphrase: String) -> PyResult<Self> {
        let config = OFIConfig {
            api_key,
            secret_key,
            passphrase,
            ..Default::default()
        };
        
        // Validate configuration
        if let Err(e) = config.validate() {
            return Err(pyo3::exceptions::PyValueError::new_err(format!("Invalid configuration: {}", e)));
        }
        
        Ok(OFIEngine { config })
    }
    
    /// Analyze a symbol for trading signals using OFI methodology.
    /// This function will block for `analysis_duration_ms` while it analyzes real-time data.
    #[pyo3(name = "analyze_symbol")]
    fn analyze_symbol_py(&self, symbol: String, imbalance_ratio: f64, analysis_duration_ms: u64, delta_threshold: f64, lookback_period_ms: u64) -> PyResult<Option<TradingSignal>> {
        // Input validation
        if symbol.is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err("Symbol cannot be empty"));
        }
        
        if symbol.len() > 20 {
            return Err(pyo3::exceptions::PyValueError::new_err("Symbol is too long: max 20 characters"));
        }
        
        if !symbol.chars().all(|c| c.is_alphanumeric() || c == '_' || c == '-' || c == '/') {
            return Err(pyo3::exceptions::PyValueError::new_err("Symbol contains invalid characters"));
        }
        
        if imbalance_ratio <= 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err("Imbalance ratio must be positive"));
        }
        
        if analysis_duration_ms == 0 || analysis_duration_ms > 3600000 { // 1 hour max
            return Err(pyo3::exceptions::PyValueError::new_err("Duration must be between 1ms and 1 hour"));
        }
        
        if delta_threshold <= 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err("Delta threshold must be positive"));
        }
        
        if lookback_period_ms == 0 || lookback_period_ms > 300000 { // 5 minutes max
            return Err(pyo3::exceptions::PyValueError::new_err("Lookback period must be between 1ms and 5 minutes"));
        }

        // Create a Tokio runtime to run our async code from a sync context
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Failed to create runtime: {}", e)))?;
            
        // Block on the async analysis function
        let result = rt.block_on(async {
            // Use the engine's configuration instead of loading from environment each time
            crate::engine::run_analysis_with_config(
                symbol, 
                imbalance_ratio, 
                analysis_duration_ms, 
                delta_threshold, 
                lookback_period_ms, 
                self.config.clone()
            ).await
        });
        
        match result {
            Ok(Some(internal_signal)) => Ok(Some(internal_signal.into())), // Convert internal signal to PyO3 class
            Ok(None) => Ok(None), // No signal found
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                "Rust engine analysis failed: {}",
                e
            ))),
        }
    }
    
    /// Get current order book for a symbol
    fn get_order_book(&self, _symbol: &str) -> PyResult<HashMap<String, f64>> {
        // Placeholder implementation
        let mut book = HashMap::new();
        book.insert("bids".to_string(), 0.0);
        book.insert("asks".to_string(), 0.0);
        Ok(book)
    }
    
    /// Get engine info (for demonstration purposes)
    #[pyo3(name = "get_engine_info")]
    fn get_engine_info(&self) -> String {
        format!("OFI Engine v{}", env!("CARGO_PKG_VERSION"))
    }
    
    /// Update configuration parameters
    #[pyo3(name = "update_config", signature = (api_key=None, secret_key=None, passphrase=None))]
    fn update_config(&mut self, api_key: Option<String>, secret_key: Option<String>, passphrase: Option<String>) {
        if let Some(key) = api_key {
            self.config.api_key = key;
        }
        if let Some(key) = secret_key {
            self.config.secret_key = key;
        }
        if let Some(pass) = passphrase {
            self.config.passphrase = pass;
        }
    }
    
    /// Get current configuration status
    #[pyo3(name = "get_config_status")]
    fn get_config_status(&self) -> String {
        let has_api_key = !self.config.api_key.is_empty();
        let has_secret_key = !self.config.secret_key.is_empty();
        let has_passphrase = !self.config.passphrase.is_empty();
        
        format!(
            "API Key: {}, Secret Key: {}, Passphrase: {}", 
            if has_api_key { "SET" } else { "NOT SET" },
            if has_secret_key { "SET" } else { "NOT SET" },
            if has_passphrase { "SET" } else { "NOT SET" }
        )
    }
    
    /// Initialize logging system
    #[pyo3(name = "init_logging", signature = (level=None))]
    fn init_logging(&self, level: Option<String>) -> PyResult<()> {
        let log_level = match level.as_deref() {
            Some("debug") | Some("DEBUG") => log::LevelFilter::Debug,
            Some("info") | Some("INFO") => log::LevelFilter::Info,
            Some("warn") | Some("WARN") => log::LevelFilter::Warn,
            Some("error") | Some("ERROR") => log::LevelFilter::Error,
            _ => log::LevelFilter::Info,
        };
        
        env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
            .filter_level(log_level)
            .try_init()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Failed to initialize logger: {}", e)))?;
        
        Ok(())
    }
}



/// Python module entry point
#[pymodule]
fn ofi_engine_rust(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Initialize the crypto provider before doing anything else
    initialize_crypto_provider();
    
    m.add_class::<TradingSignal>()?;
    m.add_class::<OFIEngine>()?;
    Ok(())
}
