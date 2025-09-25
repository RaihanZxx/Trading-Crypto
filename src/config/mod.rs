//! Configuration module for OFI engine

use serde::{Deserialize, Serialize};
use std::env;
use std::fs;
use std::path::Path;

/// TOML configuration structure
#[derive(Debug, Deserialize)]
struct TomlConfig {
    #[serde(rename = "ofi")]
    ofi_config: Option<OFITomlConfig>,
    #[serde(rename = "strategy")]
    strategy_config: Option<StrategyTomlConfig>,
}

#[derive(Debug, Deserialize)]
struct OFITomlConfig {
    #[serde(rename = "websocket_url")]
    websocket_url: Option<String>,
    #[serde(rename = "default_imbalance_threshold")]
    default_imbalance_threshold: Option<f64>,
    #[serde(rename = "default_absorption_threshold")]
    default_absorption_threshold: Option<f64>,
    #[serde(rename = "default_delta_threshold")]
    default_delta_threshold: Option<f64>,
    #[serde(rename = "default_lookback_period_ms")]
    default_lookback_period_ms: Option<u64>,
    #[serde(rename = "analysis_duration_limit_ms")]
    analysis_duration_limit_ms: Option<u64>,
    #[serde(rename = "analysis_duration_per_cycle_ms")]
    analysis_duration_per_cycle_ms: Option<u64>,
    #[serde(rename = "trade_storage_limit")]
    trade_storage_limit: Option<usize>,
    #[serde(rename = "strong_signal_confidence")]
    strong_signal_confidence: Option<f64>,
    #[serde(rename = "reversal_signal_confidence")]
    reversal_signal_confidence: Option<f64>,
    #[serde(rename = "exhaustion_signal_confidence")]
    exhaustion_signal_confidence: Option<f64>,
    #[serde(rename = "market_condition_adaptation")]
    market_condition_adaptation: Option<bool>,
    #[serde(rename = "max_concurrent_websocket_connections")]
    max_concurrent_websocket_connections: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct StrategyTomlConfig {
    #[serde(rename = "imbalance_threshold")]
    imbalance_threshold: Option<f64>,
    #[serde(rename = "absorption_threshold")]
    absorption_threshold: Option<f64>,
    #[serde(rename = "delta_threshold")]
    delta_threshold: Option<f64>,
    #[serde(rename = "lookback_period_ms")]
    lookback_period_ms: Option<u64>,
}

/// Configuration for the OFI engine
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OFIConfig {
    pub api_key: String,
    pub secret_key: String,
    pub passphrase: String,
    pub websocket_url: String,
    pub default_imbalance_threshold: f64,
    pub default_absorption_threshold: f64,
    pub default_delta_threshold: f64,
    pub default_lookback_period_ms: u64,
    pub analysis_duration_limit_ms: u64,
    pub analysis_duration_per_cycle_ms: u64,  // Duration for each analysis cycle
    pub trade_storage_limit: usize,
    pub strong_signal_confidence: f64,
    pub reversal_signal_confidence: f64,
    pub exhaustion_signal_confidence: f64,
    pub market_condition_adaptation: bool,
    pub max_concurrent_websocket_connections: Option<usize>,  // Maximum concurrent WebSocket connections
}

impl Default for OFIConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            secret_key: String::new(),
            passphrase: String::new(),
            websocket_url: String::new(),  // Harus disediakan di config.toml
            default_imbalance_threshold: 0.0,  // Harus disediakan di config.toml
            default_absorption_threshold: 0.0,  // Harus disediakan di config.toml
            default_delta_threshold: 0.0,  // Harus disediakan di config.toml
            default_lookback_period_ms: 0,  // Harus disediakan di config.toml
            analysis_duration_limit_ms: 0,  // Harus disediakan di config.toml
            analysis_duration_per_cycle_ms: 0,  // Harus disediakan di config.toml
            trade_storage_limit: 0,  // Harus disediakan di config.toml
            strong_signal_confidence: 0.0,  // Harus disediakan di config.toml
            reversal_signal_confidence: 0.0,  // Harus disediakan di config.toml
            exhaustion_signal_confidence: 0.0,  // Harus disediakan di config.toml
            market_condition_adaptation: false,  // Harus disediakan di config.toml
            max_concurrent_websocket_connections: None,  // Defaults to 20 in main.rs if not provided
        }
    }
}

impl OFIConfig {
    /// Load configuration from TOML file (non-kredensial parameters) with environment variable fallback for credentials
    pub fn from_toml_file(file_path: &str) -> Result<Self, Box<dyn std::error::Error>> {
        // Read the TOML file
        let contents = fs::read_to_string(file_path)?;
        
        // Parse the TOML contents
        let toml_config: TomlConfig = toml::from_str(&contents)?;
        
        // Create config with default values first (these will be checked later)
        let mut config = Self::default();
        
        // Apply values from TOML file if present
        if let Some(ofi_toml) = toml_config.ofi_config {
            if let Some(url) = ofi_toml.websocket_url {
                config.websocket_url = url;
            }
            if let Some(threshold) = ofi_toml.default_imbalance_threshold {
                config.default_imbalance_threshold = threshold;
            }
            if let Some(threshold) = ofi_toml.default_absorption_threshold {
                config.default_absorption_threshold = threshold;
            }
            if let Some(threshold) = ofi_toml.default_delta_threshold {
                config.default_delta_threshold = threshold;
            }
            if let Some(period) = ofi_toml.default_lookback_period_ms {
                config.default_lookback_period_ms = period;
            }
            if let Some(limit) = ofi_toml.analysis_duration_limit_ms {
                config.analysis_duration_limit_ms = limit;
            }
            if let Some(duration) = ofi_toml.analysis_duration_per_cycle_ms {
                config.analysis_duration_per_cycle_ms = duration;
            }
            if let Some(limit) = ofi_toml.trade_storage_limit {
                config.trade_storage_limit = limit;
            }
            if let Some(confidence) = ofi_toml.strong_signal_confidence {
                config.strong_signal_confidence = confidence;
            }
            if let Some(confidence) = ofi_toml.reversal_signal_confidence {
                config.reversal_signal_confidence = confidence;
            }
            if let Some(confidence) = ofi_toml.exhaustion_signal_confidence {
                config.exhaustion_signal_confidence = confidence;
            }
            if let Some(adaptation) = ofi_toml.market_condition_adaptation {
                config.market_condition_adaptation = adaptation;
            }
            if let Some(max_connections) = ofi_toml.max_concurrent_websocket_connections {
                config.max_concurrent_websocket_connections = Some(max_connections);
            }
        }
        
        // If strategy parameters are not set in [ofi] section, try to get from [strategy] section for backward compatibility
        if config.default_imbalance_threshold == 0.0 { // default value means it wasn't set from [ofi]
            if let Some(strategy_toml) = toml_config.strategy_config {
                if let Some(threshold) = strategy_toml.imbalance_threshold {
                    config.default_imbalance_threshold = threshold;
                }
                if let Some(threshold) = strategy_toml.absorption_threshold {
                    config.default_absorption_threshold = threshold;
                }
                if let Some(threshold) = strategy_toml.delta_threshold {
                    config.default_delta_threshold = threshold;
                }
                if let Some(period) = strategy_toml.lookback_period_ms {
                    config.default_lookback_period_ms = period;
                }
            }
        }
        
        // Override only credentials from environment variables (security)
        if let Ok(api_key) = env::var("BITGET_API_KEY") {
            config.api_key = api_key;
        }
        if let Ok(secret_key) = env::var("BITGET_SECRET_KEY") {
            config.secret_key = secret_key;
        }
        if let Ok(passphrase) = env::var("BITGET_PASSPHRASE") {
            config.passphrase = passphrase;
        }
        
        // Validate that all required parameters are provided (not default values)
        if config.websocket_url.is_empty() {
            return Err("websocket_url must be provided in config.toml".into());
        }
        
        if config.default_imbalance_threshold == 0.0 {
            return Err("default_imbalance_threshold must be provided in config.toml".into());
        }
        
        if config.default_absorption_threshold == 0.0 {
            return Err("default_absorption_threshold must be provided in config.toml".into());
        }
        
        if config.default_delta_threshold == 0.0 {
            return Err("default_delta_threshold must be provided in config.toml".into());
        }
        
        if config.default_lookback_period_ms == 0 {
            return Err("default_lookback_period_ms must be provided in config.toml".into());
        }
        
        if config.analysis_duration_limit_ms == 0 {
            return Err("analysis_duration_limit_ms must be provided in config.toml".into());
        }
        
        if config.analysis_duration_per_cycle_ms == 0 {
            return Err("analysis_duration_per_cycle_ms must be provided in config.toml".into());
        }
        
        if config.trade_storage_limit == 0 {
            return Err("trade_storage_limit must be provided in config.toml".into());
        }
        
        if config.strong_signal_confidence == 0.0 {
            return Err("strong_signal_confidence must be provided in config.toml".into());
        }
        
        if config.reversal_signal_confidence == 0.0 {
            return Err("reversal_signal_confidence must be provided in config.toml".into());
        }
        
        if config.exhaustion_signal_confidence == 0.0 {
            return Err("exhaustion_signal_confidence must be provided in config.toml".into());
        }
        
        // market_condition_adaptation can be false by default, so no validation needed here
        
        Ok(config)
    }

    /// Load configuration from environment variables (credentials only) - 
    /// This function is kept for compatibility but should not be used as config.toml is now required
    pub fn from_env() -> Result<Self, Box<dyn std::error::Error>> {
        let mut config = Self::default();
        
        // Only credentials are loaded from environment variables
        config.api_key = env::var("BITGET_API_KEY").unwrap_or_default();
        config.secret_key = env::var("BITGET_SECRET_KEY").unwrap_or_default();
        config.passphrase = env::var("BITGET_PASSPHRASE").unwrap_or_default();
        
        // This function should not be used as it will fail validation without config.toml parameters
        Err("from_env() should not be used - config.toml is required for all parameters".into())
    }
    
    /// Load configuration from default config.toml file and environment variables
    pub fn from_default_config() -> Result<Self, Box<dyn std::error::Error>> {
        // Try multiple possible paths for config.toml
        let possible_paths = [
            "config/config.toml",           // Relative to current working directory
            "../config/config.toml",        // From src directory to root
            "../../config/config.toml",     // Additional possible path
        ];
        
        for path in &possible_paths {
            if Path::new(path).exists() {
                // Load non-credential parameters from TOML file and credentials from environment
                return Self::from_toml_file(path);
            }
        }
        
        // If config file doesn't exist in any of the expected locations, return error
        Err("config.toml file is required and must contain all configuration parameters. Looked in: config/config.toml, ../config/config.toml, ../../config/config.toml".into())
    }
    
    /// Validate configuration parameters
    pub fn validate(&self) -> Result<(), String> {
        if self.api_key.is_empty() {
            return Err("API key is required".to_string());
        }
        
        if self.secret_key.is_empty() {
            return Err("Secret key is required".to_string());
        }
        
        if self.passphrase.is_empty() {
            return Err("Passphrase is required".to_string());
        }
        
        if self.websocket_url.is_empty() {
            return Err("WebSocket URL is required".to_string());
        }
        
        if self.default_imbalance_threshold <= 0.0 {
            return Err("Imbalance threshold must be positive".to_string());
        }
        
        if self.default_absorption_threshold <= 0.0 {
            return Err("Absorption threshold must be positive".to_string());
        }
        
        if self.default_delta_threshold <= 0.0 {
            return Err("Delta threshold must be positive".to_string());
        }
        
        if self.default_lookback_period_ms == 0 {
            return Err("Lookback period must be positive".to_string());
        }
        
        if self.analysis_duration_limit_ms == 0 {
            return Err("Analysis duration limit must be positive".to_string());
        }
        
        if self.analysis_duration_per_cycle_ms == 0 || self.analysis_duration_per_cycle_ms > self.analysis_duration_limit_ms {
            return Err(format!("Analysis duration per cycle must be positive and not exceed the limit of {}ms", self.analysis_duration_limit_ms));
        }
        
        if self.trade_storage_limit == 0 {
            return Err("Trade storage limit must be positive".to_string());
        }
        
        if self.strong_signal_confidence <= 0.0 || self.strong_signal_confidence > 1.0 {
            return Err("Strong signal confidence must be between 0 and 1".to_string());
        }
        
        if self.reversal_signal_confidence <= 0.0 || self.reversal_signal_confidence > 1.0 {
            return Err("Reversal signal confidence must be between 0 and 1".to_string());
        }
        
        if self.exhaustion_signal_confidence <= 0.0 || self.exhaustion_signal_confidence > 1.0 {
            return Err("Exhaustion signal confidence must be between 0 and 1".to_string());
        }
        
        Ok(())
    }
}