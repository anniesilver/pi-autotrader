"""Option pricing helpers shared by the engine (estimates) and the replay broker."""

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0.0001:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def target_call_strike(price: float, vix: float, cfg) -> float:
    """Strike the strategy aims for: max(min distance, VIX * scaling) out of the money."""
    otm = max(cfg.min_strike_distance, vix * cfg.volatility_scaling_factor)
    step = cfg.strike_rounding
    return round(price * (1 + otm) / step) * step


def estimate_call_premium(price: float, strike: float, days: int, vix: float, cfg) -> float:
    """Black-Scholes with VIX as implied vol, same as the backtest."""
    if vix is None or vix <= 0 or math.isnan(vix):
        vix = 0.20
    days = max(1, days)
    return black_scholes_call(price, strike, days / 365.0, cfg.risk_free_rate, vix)
