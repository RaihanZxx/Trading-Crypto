import time
import threading
from typing import Dict, List, Optional
from connectors.exchange_service import BitgetExchangeService
from dataclasses import dataclass
from enum import Enum


class MarketCondition(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    CHOPPY = "choppy"
    CONSOLIDATING = "consolidating"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


@dataclass
class MarketMetrics:
    symbol: str
    volatility: float
    trend_strength: float
    momentum: float
    rsi: float
    volume_ratio: float
    timestamp: float


class MarketConditionAnalyzer:
    """Analyzes market conditions to adapt trading strategies."""
    
    def __init__(self, exchange: BitgetExchangeService):
        self.exchange = exchange
        self.metrics_cache = {}
        self.cache_duration = 300  # 5 minutes cache
        self.lock = threading.Lock()
        
    def get_market_condition(self, symbol: str) -> MarketCondition:
        """Get the current market condition for a symbol."""
        with self.lock:
            # Check if we have fresh metrics in cache
            cached = self.metrics_cache.get(symbol)
            if cached and (time.time() - cached.timestamp) < self.cache_duration:
                return self._classify_market_condition(cached)
        
        # Calculate fresh metrics
        metrics = self._calculate_metrics(symbol)
        
        # Cache the metrics
        with self.lock:
            self.metrics_cache[symbol] = metrics
        
        return self._classify_market_condition(metrics)
    
    def _calculate_metrics(self, symbol: str) -> MarketMetrics:
        """Calculate various market metrics."""
        # Get historical price data (last 100 periods)
        try:
            candles = self.exchange.get_candlesticks(symbol, limit=100, granularity="1H")
        except Exception:
            # If we can't get historical data, return default metrics
            return MarketMetrics(
                symbol=symbol,
                volatility=0.02,  # 2% default
                trend_strength=0.0,
                momentum=0.0,
                rsi=50.0,
                volume_ratio=1.0,
                timestamp=time.time()
            )
        
        if not candles or len(candles) < 20:  # Need at least 20 data points
            return MarketMetrics(
                symbol=symbol,
                volatility=0.02,
                trend_strength=0.0,
                momentum=0.0,
                rsi=50.0,
                volume_ratio=1.0,
                timestamp=time.time()
            )
        
        # Convert candles to numerical data [open, high, low, close, volume, ...]
        prices = []
        volumes = []
        for candle in candles:
            if len(candle) >= 5:  # [timestamp, open, high, low, close, volume, ...]
                prices.append(float(candle[4]))  # close price
                volumes.append(float(candle[5]))  # volume
        
        if len(prices) < 2:
            return MarketMetrics(
                symbol=symbol,
                volatility=0.02,
                trend_strength=0.0,
                momentum=0.0,
                rsi=50.0,
                volume_ratio=1.0,
                timestamp=time.time()
            )
        
        # Calculate volatility (std dev of returns)
        returns = [prices[i]/prices[i-1] - 1 for i in range(1, len(prices))]
        volatility = sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)
        volatility = volatility**0.5
        
        # Calculate trend strength (how consistently prices move in one direction)
        positive_returns = sum(1 for r in returns if r > 0)
        trend_strength = abs(2 * (positive_returns / len(returns)) - 1)  # -1 to 1, centered at 0
        
        # Calculate momentum (price change over recent periods)
        momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0.0
        
        # Calculate RSI (simplified)
        rsi = self._calculate_rsi(prices)
        
        # Calculate volume ratio compared to average
        avg_volume = sum(volumes) / len(volumes) if volumes else 1.0
        current_volume = volumes[-1] if volumes else 1.0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        return MarketMetrics(
            symbol=symbol,
            volatility=volatility,
            trend_strength=trend_strength,
            momentum=momentum,
            rsi=rsi,
            volume_ratio=volume_ratio,
            timestamp=time.time()
        )
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0  # Neutral RSI if not enough data
        
        gains = []
        losses = []
        
        for i in range(1, min(len(prices), period + 1)):
            change = prices[-i] - prices[-i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / len(gains) if gains else 0.01
        avg_loss = sum(losses) / len(losses) if losses else 0.01
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _classify_market_condition(self, metrics: MarketMetrics) -> MarketCondition:
        """Classify market condition based on metrics."""
        volatility = metrics.volatility
        trend_strength = metrics.trend_strength
        momentum = metrics.momentum
        rsi = metrics.rsi
        volume_ratio = metrics.volume_ratio
        
        # High volatility condition
        if volatility > 0.05:  # > 5% volatility
            return MarketCondition.HIGH_VOLATILITY
        
        # Low volatility condition
        if volatility < 0.01:  # < 1% volatility
            return MarketCondition.LOW_VOLATILITY
        
        # Strong trend conditions
        if trend_strength > 0.7:
            if momentum > 0.02:  # 2% positive momentum
                return MarketCondition.BULLISH
            elif momentum < -0.02:  # 2% negative momentum
                return MarketCondition.BEARISH
        
        # RSI-based conditions
        if rsi > 70:  # Overbought
            return MarketCondition.CHOPPY
        elif rsi < 30:  # Oversold
            return MarketCondition.CHOPPY
        
        # Volume-based conditions
        if volume_ratio > 2.0:  # 2x average volume
            if momentum > 0:
                return MarketCondition.BULLISH
            else:
                return MarketCondition.BEARISH
        
        # Default to consolidating for neutral conditions
        return MarketCondition.CONSOLIDATING
    
    def get_adapted_strategy_params(self, symbol: str) -> Dict:
        """Get strategy parameters adapted to current market condition."""
        condition = self.get_market_condition(symbol)
        
        # Default parameters
        params = {
            'imbalance_threshold_multiplier': 1.0,
            'delta_threshold_multiplier': 1.0,
            'stop_loss_multiplier': 1.0,
            'position_size_multiplier': 1.0,
            'min_trade_confidence': 0.7,
        }
        
        if condition == MarketCondition.HIGH_VOLATILITY:
            # Be more conservative in high volatility
            params.update({
                'imbalance_threshold_multiplier': 1.5,  # Require stronger imbalances
                'delta_threshold_multiplier': 1.5,      # Require stronger momentum
                'stop_loss_multiplier': 1.2,            # Wider stops
                'position_size_multiplier': 0.7,        # Smaller positions
                'min_trade_confidence': 0.8,            # Higher confidence required
            })
        elif condition == MarketCondition.LOW_VOLATILITY:
            # Be more aggressive in low volatility
            params.update({
                'imbalance_threshold_multiplier': 0.8,  # Accept weaker imbalances
                'delta_threshold_multiplier': 0.8,      # Accept weaker momentum
                'stop_loss_multiplier': 0.8,            # Tighter stops
                'position_size_multiplier': 1.2,        # Larger positions
                'min_trade_confidence': 0.6,            # Lower confidence threshold
            })
        elif condition == MarketCondition.BULLISH:
            params.update({
                'min_trade_confidence': 0.65,
                'position_size_multiplier': 1.1,
            })
        elif condition == MarketCondition.BEARISH:
            params.update({
                'min_trade_confidence': 0.65,
                'position_size_multiplier': 1.1,
            })
        elif condition == MarketCondition.CHOPPY:
            # Reduce risk in choppy conditions
            params.update({
                'imbalance_threshold_multiplier': 1.3,
                'delta_threshold_multiplier': 1.3,
                'position_size_multiplier': 0.8,
                'min_trade_confidence': 0.8,
            })
        elif condition == MarketCondition.CONSOLIDATING:
            # More conservative during consolidation
            params.update({
                'position_size_multiplier': 0.9,
                'min_trade_confidence': 0.75,
            })
        
        return params


# Global instance for the application
market_analyzer = None


def initialize_market_analyzer(exchange: BitgetExchangeService):
    """Initialize the global market analyzer instance."""
    global market_analyzer
    market_analyzer = MarketConditionAnalyzer(exchange)


def get_market_analyzer():
    """Get the global market analyzer instance."""
    return market_analyzer