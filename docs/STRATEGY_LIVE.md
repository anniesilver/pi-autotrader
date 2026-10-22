# SPY_POWER_CASHFLOW: live rules

Source of truth for the rules is `algo_trading/SPY_POWER_CASHFLOW` (`config.py`, `trading_simulator.py`, `position.py`). `autotrader/engine.py` re-implements them as a function the bot calls once per trading day, shortly before the close (planned 15:45 ET), using the current SPY price and VIX.

## Rules

| When | Rule | Default |
|---|---|---|
| First run, no shares | Buy `initial_position_percent` of equity | 60% |
| First run in a new month | Sell covered calls on all uncovered shares, expiring the month's last trading day | strike = max(1.5%, VIX × 0.15) OTM, rounded to $5 |
| Every run | Track the high since the last buy | |
| Every run | If leverage (position ÷ equity) is above the limit: buy back calls on shares that will be sold (highest strike first), then sell shares down to the limit; keep at least 10% of shares | limit 2.0; 1.5 when VIX ≥ 25; 1.25 when VIX ≥ 40 |
| Every run | Dip buy when price ≤ trigger × high, using a share of buying power (2 × equity − position) | −8% / 40%; when VIX ≥ 25: −20% / 15% |
| Last trading day of month | Buy back expiring ITM calls at the close (sell shares only if buying power can't fund it); let OTM calls expire | |
| Last trading day of month | Withdraw a percent of equity | 1% |

## Parity with the backtest

`backtest/replay.py` runs the engine over the same 20-year data with a simulated broker that fills at the engine's estimates. From 2006-01-01 the replay ends at $1,344,852 against the original backtest's $1,345,317 (0.035% apart, largest daily gap 0.035%). Starting in 2018 the gap is 0.3%. The difference comes from one ordering detail: the backtest charges the first day's margin interest after the monthly premium is credited, the replay charges it before the engine runs.

## Where live trading will differ (to watch in paper trading)

- **Premiums are real quotes, not Black-Scholes on VIX.** VIX is 30-day S&P implied vol; the real IV at the target strike is usually lower (skew), so actual premiums will likely come in below the backtest.
- **Strikes and expiries must exist.** SPY has daily expirations and $1 strikes, so the month-end expiry and $5-rounded strike should always be listed, but the bot will verify against the option chain.
- **Early assignment.** Deep ITM calls can be assigned early, especially the day before SPY's quarterly ex-dividend date (March, June, September, December). The backtest never models this. The bot needs to notice assignments and rebuy or rebalance.
- **Withdrawals.** A paper account can't withdraw cash. The bot will record withdrawals as a virtual ledger and subtract them from cash when building each snapshot, so leverage matches the backtest.
- **Equity definition.** The backtest uses cash + shares × price and ignores the short calls' market value; IB's NetLiquidation includes it. The bot will build snapshots the backtest way for consistency, and log IB's own numbers alongside.
- **Margin interest and dividends** are handled by IB itself; the backtest's 6% interest is an assumption. Dividends are not in the backtest data at all.
- **Known backtest quirk carried over:** `get_buying_power` computes an assignment buffer (`CALL_COST_BUFFER`) but never subtracts it, so buying power ignores open ITM calls. The engine keeps that behaviour for parity; worth deciding whether to fix it before going live.
- The repo README says "covered call + sell put", but the code only sells calls; the engine follows the code.
