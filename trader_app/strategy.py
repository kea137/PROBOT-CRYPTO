from __future__ import annotations

import pandas as pd


def add_moving_averages(
    frame: pd.DataFrame, short_window: int, long_window: int
) -> pd.DataFrame:
    if short_window <= 0 or long_window <= 0:
        raise ValueError("Moving-average windows must be positive integers.")

    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window.")

    analyzed = frame.copy()
    analyzed["ma_short"] = analyzed["close"].rolling(short_window).mean()
    analyzed["ma_long"] = analyzed["close"].rolling(long_window).mean()
    return analyzed


def latest_signal(frame: pd.DataFrame) -> str:
    latest = frame.iloc[-1]

    if pd.isna(latest["ma_short"]) or pd.isna(latest["ma_long"]):
        raise ValueError("Not enough data to compute the configured moving averages.")

    return "BUY" if latest["ma_short"] > latest["ma_long"] else "SELL"
