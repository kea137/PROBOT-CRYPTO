#!/usr/bin/env python3
"""Quick parameter sweep with pre-computed indicators."""
import sys
import time

import numpy as np
import pandas as pd

from trader_app.strategy import (
    add_moving_averages,
    compute_atr,
    compute_bollinger_bands,
    compute_confluence_score,
    compute_macd,
    compute_price_position,
    compute_rsi,
    compute_trailing_stop,
    compute_volatility_position_size,
    has_volume_confirmation,
)
from backtest import FeeModel, Trade, BacktestConfig, analyze


def fetch_data(symbol="BTC/USDT", timeframe="4h", days=365):
    import ccxt
    exchange = ccxt.bybit({"enableRateLimit": True})
    tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
             "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
    candle_ms = tf_ms.get(timeframe, 14_400_000)
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - days * 86_400_000
    all_bars = []
    cursor = since_ms
    print(f"  Fetching {symbol} {timeframe} ({days}d)…")
    while cursor < now_ms:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
        if not bars:
            break
        all_bars.extend(bars)
        if bars[-1][0] <= cursor:
            break
        cursor = bars[-1][0] + candle_ms
        time.sleep(exchange.rateLimit / 1000)
    df = pd.DataFrame(all_bars, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    print(f"  Got {len(df)} candles")
    return df


def precompute(df, short_w=20, long_w=50):
    """Pre-compute all indicators once for the entire dataframe."""
    analyzed = add_moving_averages(df.copy(), short_w, long_w)
    analyzed["atr"] = compute_atr(analyzed, 14)
    analyzed["rsi"] = compute_rsi(analyzed["close"], 14)
    bb_u, bb_m, bb_l = compute_bollinger_bands(analyzed["close"], 20, 2.0)
    analyzed["bb_upper"] = bb_u
    analyzed["bb_lower"] = bb_l
    macd_line, macd_signal, macd_hist = compute_macd(analyzed["close"])
    analyzed["macd_hist"] = macd_hist

    # Signal: BUY if ma_short > ma_long, else SELL
    analyzed["signal"] = np.where(analyzed["ma_short"] > analyzed["ma_long"], "BUY", "SELL")

    # Momentum
    analyzed["momentum"] = analyzed["close"].diff()

    # Long MA slope (2-bar lookback)
    analyzed["long_ma_slope"] = analyzed["ma_long"].diff(2)

    # Volume avg
    vol_avg = analyzed["volume"].rolling(20, min_periods=1).mean()
    analyzed["vol_confirmed"] = analyzed["volume"] >= vol_avg

    # Price position (rolling 20)
    roll_low = analyzed["close"].rolling(20, min_periods=1).min()
    roll_high = analyzed["close"].rolling(20, min_periods=1).max()
    rng = (roll_high - roll_low).replace(0, 1.0)
    analyzed["price_position"] = (analyzed["close"] - roll_low) / rng

    # Confluence score (simplified — count indicators aligned with signal)
    # RSI alignment, MACD histogram, BB position, volume
    rsi = analyzed["rsi"]
    analyzed["confluence"] = 0
    for idx in range(len(analyzed)):
        sig = analyzed["signal"].iloc[idx]
        score = 0
        if sig == "BUY":
            if rsi.iloc[idx] < 70: score += 1
            if analyzed["macd_hist"].iloc[idx] > 0: score += 1
            if analyzed["close"].iloc[idx] < bb_m.iloc[idx]: score += 1
        else:
            if rsi.iloc[idx] > 30: score += 1
            if analyzed["macd_hist"].iloc[idx] < 0: score += 1
            if analyzed["close"].iloc[idx] > bb_m.iloc[idx]: score += 1
        if analyzed["vol_confirmed"].iloc[idx]: score += 1
        analyzed.iloc[idx, analyzed.columns.get_loc("confluence")] = score

    return analyzed


def fast_backtest(analyzed, cfg, fee_model=None):
    """Run backtest using pre-computed indicators."""
    fees = fee_model or FeeModel()
    trades = []
    equity = cfg.initial_equity
    eq_curve = []

    in_position = False
    entry_signal = ""
    entry_price = 0.0
    entry_amount = 0.0
    entry_cost_total = 0.0
    entry_bar = 0
    sl_price = 0.0
    tp_price = 0.0
    trail_ext = 0.0

    start = cfg.long_window + 50
    n = len(analyzed)

    closes = analyzed["close"].values
    signals = analyzed["signal"].values
    atr_vals = analyzed["atr"].values
    momentum = analyzed["momentum"].values
    macd_hist = analyzed["macd_hist"].values
    long_ma_slope = analyzed["long_ma_slope"].values
    price_pos = analyzed["price_position"].values
    confluence = analyzed["confluence"].values
    vol_conf = analyzed["vol_confirmed"].values
    times = analyzed["time"].values

    for i in range(start, n):
        close = closes[i]
        sig = signals[i]
        atr = atr_vals[i]
        mom = momentum[i]
        mhist = macd_hist[i]
        slope = long_ma_slope[i]
        pp = price_pos[i]
        conf = int(confluence[i])
        vc = vol_conf[i]

        if in_position:
            exit_now = False
            reason = "hold"

            if entry_signal == "BUY":
                if close <= entry_price * (1 - cfg.stop_loss):
                    exit_now, reason = True, "stop_loss"
                elif close >= entry_price * (1 + cfg.take_profit):
                    exit_now, reason = True, "take_profit"

                if cfg.use_atr_stops and atr > 0:
                    if close <= sl_price:
                        exit_now, reason = True, "stop_loss_atr"
                    elif close >= tp_price:
                        exit_now, reason = True, "take_profit_atr"

                if cfg.use_trailing_stop and atr > 0:
                    if close > trail_ext:
                        trail_ext = close
                    ts = compute_trailing_stop(trail_ext, atr, cfg.trail_atr_multiplier)
                    if close <= ts:
                        exit_now, reason = True, "trailing_stop"

                bars_held = i - entry_bar
                if not exit_now and bars_held >= cfg.min_hold_bars:
                    if sig == "SELL":
                        exit_now, reason = True, "signal_flip"
                    elif mom < 0:
                        exit_now, reason = True, "negative_momentum"

            elif entry_signal == "SELL":
                if close >= entry_price * (1 + cfg.stop_loss):
                    exit_now, reason = True, "stop_loss"
                elif close <= entry_price * (1 - cfg.take_profit):
                    exit_now, reason = True, "take_profit"

                if cfg.use_atr_stops and atr > 0:
                    if close >= sl_price:
                        exit_now, reason = True, "stop_loss_atr"
                    elif close <= tp_price:
                        exit_now, reason = True, "take_profit_atr"

                if cfg.use_trailing_stop and atr > 0:
                    if close < trail_ext:
                        trail_ext = close
                    ts = compute_trailing_stop(trail_ext, atr, cfg.trail_atr_multiplier, is_short=True)
                    if close >= ts:
                        exit_now, reason = True, "trailing_stop"

                bars_held = i - entry_bar
                if not exit_now and bars_held >= cfg.min_hold_bars:
                    if sig == "BUY":
                        exit_now, reason = True, "signal_flip"

            if exit_now:
                if entry_signal == "BUY":
                    exit_p = fees.market_sell_price(close)
                    gross = (exit_p - entry_price) * entry_amount
                else:
                    exit_p = fees.market_buy_price(close)
                    gross = (entry_price - exit_p) * entry_amount

                entry_fee = entry_cost_total - entry_price * entry_amount
                exit_fee = exit_p * entry_amount * fees.taker_pct
                tot_fees = entry_fee + exit_fee
                slip = close * entry_amount * fees.slippage_pct * 2
                net = gross - tot_fees - slip

                equity += net
                trades.append(Trade(
                    entry_time=times[entry_bar], exit_time=times[i],
                    side=entry_signal, entry_price=entry_price,
                    exit_price=exit_p, amount=entry_amount,
                    gross_pnl=gross, fees=tot_fees,
                    slippage_cost=slip, net_pnl=net,
                    exit_reason=reason, hold_bars=i - entry_bar,
                ))
                in_position = False

        if not in_position:
            # Entry logic
            raw_conf = conf
            if cfg.volume_confirmation and not vc:
                raw_conf = max(0, raw_conf - 1)

            if cfg.confluence_threshold > 0 and raw_conf < cfg.confluence_threshold:
                eq_curve.append({"time": times[i], "equity": equity, "close": close})
                continue

            enter = False
            if sig == "BUY":
                if slope >= 0 and pp < 0.92 and mhist >= 0:
                    enter = True
            elif sig == "SELL" and cfg.allow_short:
                if slope <= 0 and pp > 0.08 and mhist <= 0:
                    enter = True

            if enter and atr > 0:
                if cfg.use_atr_sizing:
                    amount = compute_volatility_position_size(equity, close, atr, cfg.atr_risk_pct)
                else:
                    amount = cfg.order_amount

                est = close * amount * (1 + fees.taker_pct + fees.slippage_pct)
                if est > equity * 0.95:
                    amount = (equity * 0.95) / (close * (1 + fees.taker_pct + fees.slippage_pct))

                if amount > 0:
                    is_short = sig == "SELL"
                    entry_price = fees.market_buy_price(close) if not is_short else fees.market_sell_price(close)
                    entry_cost_total = fees.entry_cost(entry_price, amount)
                    entry_amount = amount
                    entry_signal = sig
                    entry_bar = i
                    in_position = True
                    trail_ext = entry_price

                    if cfg.use_atr_stops and atr > 0:
                        from trader_app.strategy import compute_atr_stops
                        sl_price, tp_price = compute_atr_stops(
                            entry_price, atr, cfg.atr_sl_multiplier, cfg.atr_tp_multiplier, is_short)
                    else:
                        if is_short:
                            sl_price = entry_price * (1 + cfg.stop_loss)
                            tp_price = entry_price * (1 - cfg.take_profit)
                        else:
                            sl_price = entry_price * (1 - cfg.stop_loss)
                            tp_price = entry_price * (1 + cfg.take_profit)

        eq_curve.append({"time": times[i], "equity": equity, "close": close})

    # Force close
    if in_position:
        close = closes[-1]
        if entry_signal == "BUY":
            exit_p = fees.market_sell_price(close)
            gross = (exit_p - entry_price) * entry_amount
        else:
            exit_p = fees.market_buy_price(close)
            gross = (entry_price - exit_p) * entry_amount
        entry_fee = entry_cost_total - entry_price * entry_amount
        exit_fee = exit_p * entry_amount * fees.taker_pct
        net = gross - entry_fee - exit_fee - close * entry_amount * fees.slippage_pct * 2
        equity += net
        trades.append(Trade(
            entry_time=times[entry_bar], exit_time=times[-1],
            side=entry_signal, entry_price=entry_price,
            exit_price=exit_p, amount=entry_amount,
            gross_pnl=gross, fees=entry_fee + exit_fee,
            slippage_cost=close * entry_amount * fees.slippage_pct * 2,
            net_pnl=net, exit_reason="force_close",
            hold_bars=len(analyzed) - 1 - entry_bar,
        ))

    eq_df = pd.DataFrame(eq_curve) if eq_curve else pd.DataFrame(columns=["time", "equity", "close"])
    return trades, eq_df


def main():
    df = fetch_data("BTC/USDT", "4h", 365)
    analyzed = precompute(df, 20, 50)
    fees = FeeModel()

    results = []
    configs_tested = 0

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
                        configs_tested += 1
                        if trades:
                            m = analyze(trades, eq, c)
                            results.append((m, c))

    print(f"\n  Tested {configs_tested} configurations\n")

    results.sort(key=lambda x: (x[0]["sharpe_ratio"], x[0]["roi_pct"]), reverse=True)

    print(f"  {'#':<4} {'CT':>3} {'MH':>3} {'SL':>5} {'TP':>5} {'Trail':>6} {'Trades':>7} {'Win%':>6} {'ROI%':>8} {'MaxDD%':>7} {'Sharpe':>7}")
    print(f"  {'─'*4} {'─'*3} {'─'*3} {'─'*5} {'─'*5} {'─'*6} {'─'*7} {'─'*6} {'─'*8} {'─'*7} {'─'*7}")
    for i, (m, c) in enumerate(results[:20], 1):
        print(f"  {i:<4} {c.confluence_threshold:>3} {c.min_hold_bars:>3} "
              f"{c.atr_sl_multiplier:>5.1f} {c.atr_tp_multiplier:>5.1f} {c.trail_atr_multiplier:>6.1f} "
              f"{m['total_trades']:>7} {m['win_rate_pct']:>5.1f}% {m['roi_pct']:>+7.2f}% "
              f"{m['max_drawdown_pct']:>6.2f}% {m['sharpe_ratio']:>7.3f}")

    if results:
        best_m, best_c = results[0]
        print(f"\n  BEST CONFIG:")
        print(f"    confluence_threshold = {best_c.confluence_threshold}")
        print(f"    min_hold_bars        = {best_c.min_hold_bars}")
        print(f"    atr_sl_multiplier    = {best_c.atr_sl_multiplier}")
        print(f"    atr_tp_multiplier    = {best_c.atr_tp_multiplier}")
        print(f"    trail_atr_multiplier = {best_c.trail_atr_multiplier}")
        print(f"\n  METRICS:")
        for k, v in best_m.items():
            print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
