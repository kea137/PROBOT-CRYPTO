#!/usr/bin/env python3
"""Quick targeted sweep — filter for 10+ trades."""
import sys
sys.path.insert(0, ".")
from sweep import fetch_data, precompute, fast_backtest, FeeModel
from backtest import BacktestConfig, analyze

df = fetch_data("BTC/USDT", "4h", 365)
analyzed = precompute(df, 20, 50)
fees = FeeModel()

results = []
for ct in [2, 3, 4]:
    for mh in [1, 3, 6, 10]:
        for atr_sl in [1.5, 2.0, 3.0]:
            for atr_tp in [2.0, 3.0, 4.0, 5.0]:
                for trail in [1.5, 2.0, 3.0]:
                    c = BacktestConfig(
                        confluence_threshold=ct,
                        atr_sl_multiplier=atr_sl,
                        atr_tp_multiplier=atr_tp,
                        trail_atr_multiplier=trail,
                        min_hold_bars=mh,
                    )
                    trades, eq = fast_backtest(analyzed, c, fees)
                    if trades and len(trades) >= 10:
                        m = analyze(trades, eq, c)
                        results.append((m, c))

results.sort(key=lambda x: (x[0]["sharpe_ratio"], x[0]["roi_pct"]), reverse=True)

print(f"\nConfigs with 10+ trades: {len(results)}")
print(f"  {'#':<4} {'CT':>3} {'MH':>3} {'SL':>5} {'TP':>5} {'Trail':>6} {'Trades':>7} {'Win%':>6} {'ROI%':>8} {'MaxDD%':>7} {'Sharpe':>7} {'PF':>6} {'FeePct':>7}")
for i, (m, c) in enumerate(results[:20], 1):
    print(f"  {i:<4} {c.confluence_threshold:>3} {c.min_hold_bars:>3} "
          f"{c.atr_sl_multiplier:>5.1f} {c.atr_tp_multiplier:>5.1f} {c.trail_atr_multiplier:>6.1f} "
          f"{m['total_trades']:>7} {m['win_rate_pct']:>5.1f}% {m['roi_pct']:>+7.2f}% "
          f"{m['max_drawdown_pct']:>6.2f}% {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>5.3f} {m['fees_pct_of_gross']:>6.1f}%")

if results:
    best_m, best_c = results[0]
    print(f"\n  BEST CONFIG (10+ trades):")
    print(f"    confluence_threshold = {best_c.confluence_threshold}")
    print(f"    min_hold_bars        = {best_c.min_hold_bars}")
    print(f"    atr_sl_multiplier    = {best_c.atr_sl_multiplier}")
    print(f"    atr_tp_multiplier    = {best_c.atr_tp_multiplier}")
    print(f"    trail_atr_multiplier = {best_c.trail_atr_multiplier}")
    for k, v in best_m.items():
        print(f"    {k}: {v}")
