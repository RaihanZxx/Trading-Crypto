import threading
from typing import Optional


class PortfolioRiskTracker:
    """Tracks portfolio-level risk metrics."""
    def __init__(self, max_portfolio_risk: float = 0.05):  # 5% max portfolio risk
        self.max_portfolio_risk = max_portfolio_risk
        self.lock = threading.Lock()
    
    def check_portfolio_risk(self, current_positions_value: float, total_balance: float) -> tuple[bool, str]:
        """
        Check if opening a new position would exceed portfolio risk limits.
        Returns (is_safe, reason_message)
        """
        if total_balance <= 0:
            return False, "Total balance is zero or negative"
        
        portfolio_risk_percentage = current_positions_value / total_balance
        
        if portfolio_risk_percentage > self.max_portfolio_risk:
            return False, f"Portfolio risk would exceed {self.max_portfolio_risk*100:.2f}% (current: {portfolio_risk_percentage*100:.2f}%)"
        
        return True, "Portfolio risk within acceptable limits"