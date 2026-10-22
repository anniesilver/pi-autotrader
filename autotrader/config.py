"""Strategy settings for SPY_POWER_CASHFLOW.

Defaults mirror algo_trading/SPY_POWER_CASHFLOW/config.py so the live engine
makes the same decisions the backtest did.
"""

from dataclasses import dataclass


@dataclass
class StrategyConfig:
    symbol: str = "SPY"

    # Leverage (position_value / equity)
    max_margin_ratio: float = 2.0
    initial_position_percent: float = 0.6

    # Dip buying
    dip_trigger: float = 0.92  # buy when price <= 92% of high since last buy
    dip_buy_percent: float = 0.4  # share of buying power deployed per dip

    # VIX-tiered dip buying
    vix_high_threshold: float = 0.25
    high_vix_dip_trigger: float = 0.80
    high_vix_dip_buy_percent: float = 0.15

    # VIX-tiered proactive deleveraging
    vix_deleverage_threshold: float = 0.25
    vix_deleverage_target_ratio: float = 1.5
    extreme_vix: float = 0.40

    # Covered calls
    contract_size: int = 100
    min_strike_distance: float = 0.015
    volatility_scaling_factor: float = 0.15
    strike_rounding: float = 5.0
    covered_call_ratio: float = 1.0
    risk_free_rate: float = 0.05

    # Costs (used for sizing and by the replay broker)
    stock_commission: float = 0.01
    option_commission: float = 0.65
    min_commission: float = 1.00
    margin_interest_rate: float = 0.06

    # Monthly withdrawal, percent of equity (1.0 = 1%)
    monthly_withdrawal_rate: float = 1.0
