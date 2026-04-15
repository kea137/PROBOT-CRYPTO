# Crypto Trading Bot — Comprehensive Guide

This document explains the trading strategy, risk management features, and
recommended configurations for generating profits on cryptocurrency markets.

---

## Table of Contents

1. [Strategy Overview](#strategy-overview)
2. [Technical Indicators](#technical-indicators)
3. [Entry Logic](#entry-logic)
4. [Exit Logic](#exit-logic)
5. [Risk Management](#risk-management)
6. [Position Sizing](#position-sizing)
7. [Configuration Reference](#configuration-reference)
8. [Recommended Commands](#recommended-commands)
9. [Optimization Tips](#optimization-tips)
10. [Backtesting and Validation](#backtesting-and-validation)

---

## Strategy Overview

The bot uses a **multi-indicator confluence** approach to identify high-probability
trades in crypto markets. Rather than relying on a single moving-average crossover,
it combines several independent signals and only enters a trade when enough of them
agree (configurable via `--confluence-threshold`).

### Signal Flow

```
OHLCV Data → Moving Averages → Primary Signal (BUY/SELL)
                ↓
        Technical Indicators:
          RSI, MACD, ADX, Bollinger Bands, Volume
                ↓
        Confluence Scoring (0–5)
                ↓
        Order-Book Confirmation
                ↓
        Risk Filters (drawdown, cooldown, volume)
                ↓
        Trade Execution or WAIT
```

---

## Technical Indicators

| Indicator | Purpose | Default Period |
|-----------|---------|---------------|
| **SMA Crossover** | Primary trend direction (short MA vs long MA) | 50 / 200 |
| **RSI** | Overbought / oversold filter | 14 |
| **MACD** | Momentum confirmation via histogram direction | 12 / 26 / 9 |
| **ADX** | Trend strength — only trade when market is trending | 14 |
| **Bollinger Bands** | Mean-reversion guard — avoid buying at the top band | 20 |
| **ATR** | Volatility-based stop-loss and take-profit distances | 14 |
| **VWAP** | Fair-value reference for intraday entries | cumulative |
| **Volume Ratio** | Confirm participation — avoid low-volume fakeouts | 20 |
| **Order Book** | Real-time buy/sell pressure from bid/ask depth | 5 levels |

### Confluence Scoring

When `--confluence-threshold` is set (recommended: **2–3**), the bot counts how many
of these independent checks agree with the proposed signal:

1. **RSI alignment** — RSI < 65 for BUY, RSI > 35 for SELL
2. **MACD histogram** — positive for BUY, negative for SELL
3. **ADX + direction** — trending (>25) with directional movement aligned
4. **Bollinger position** — not overbought for BUY, not oversold for SELL
5. **Volume** — current bar volume ≥ 20-period average

A score of **3 or higher** indicates strong confluence and higher win rate.

---

## Entry Logic

A trade is opened when **all** of the following conditions are met:

1. **Primary signal** — short MA above long MA → BUY; below → SELL
2. **Order-book bias** — bid volume supports the direction (or extreme price position overrides)
3. **Long MA slope** — positive for BUY, negative for SELL (trend alignment)
4. **Price position** — not at an extreme (< 0.92 for BUY, > 0.08 for SELL)
5. **MACD confirmation** — histogram agrees with direction (when order book is neutral)
6. **Confluence threshold** — enough independent indicators agree (if configured)
7. **Volume confirmation** — current volume at or above average (if `--volume-confirmation` is set)
8. **RSI filter** — not overbought for BUY, not oversold for SELL (if `--rsi-filter` is set)
9. **ADX filter** — market is trending above minimum strength (if `--min-adx` is set)
10. **Loss cooldown** — enough time has passed since last losing trade (if `--loss-cooldown` is set)
11. **ML bias** — XGBoost model agrees with direction (if `--use-xgboost` is set)

### Short Selling

Short entries require `--allow-short` and follow the inverse of the BUY logic.
Short selling is riskier in crypto due to unlimited upside risk and funding rates.
Only enable this when you have confirmed the strategy on demo.

---

## Exit Logic

### For Long Positions

The bot exits a long position when any of these conditions trigger:

| Condition | Description |
|-----------|-------------|
| **Stop-loss** | Price drops below entry × (1 − stop_loss) |
| **Take-profit** | Price rises above entry × (1 + take_profit) |
| **Signal flip** | Short MA crosses below long MA |
| **Sell pressure** | Order-book ask volume dominates bid volume |
| **Negative momentum** | Price momentum turns negative with sell pressure |
| **Max hold** | Position held longer than `--max-hold` duration |
| **ML signal** | XGBoost model flips to SELL (if enabled) |
| **ATR trailing stop** | Price drops below highest-close minus ATR distance (if enabled) |

### For Short Positions

Inverse of long exit logic — exits on BUY signals, buy pressure, positive
momentum, or stop/take-profit hits.

---

## Risk Management

### Stop-Loss and Take-Profit

**Fixed percentage** (default):
- `--stop-loss 0.01` — exit if position loses 1%
- `--take-profit 0.02` — exit if position gains 2%

**ATR-based** (recommended for crypto volatility):
- `--use-atr-stops` — replace fixed SL/TP with ATR multiples
- `--atr-sl-multiplier 2.0` — stop-loss at 2× ATR below entry
- `--atr-tp-multiplier 3.0` — take-profit at 3× ATR above entry
- Produces a 1:1.5 risk-reward ratio by default

### Trailing Stop

- `--use-trailing-stop` — ratchet stop upward as price moves in your favor
- `--trail-atr-multiplier 2.0` — trail distance = 2× ATR from the highest close
- Lets winners run while protecting profits

### Drawdown Protection

- `--max-drawdown 0.05` — stop the bot entirely if equity falls 5% from its peak
- Prevents catastrophic losses during market crashes
- The bot logs the drawdown percentage and terminates cleanly

### Daily Loss Limit

- `--max-daily-loss 0.03` — halt trading if 3% of starting equity is lost in one day
- Prevents revenge trading and tilt-based decisions

### Loss Cooldown

- `--loss-cooldown 300` — wait 5 minutes after a losing trade before entering again
- Avoids consecutive entries in choppy markets

---

## Position Sizing

### Fixed Size

`--order-amount 0.001` — always trade 0.001 BTC per entry.

### ATR-Based Volatility Sizing (recommended)

`--use-atr-sizing --atr-risk-pct 0.01`

This calculates position size so that **one ATR of adverse price movement** risks
exactly 1% of your total equity. In volatile markets, positions are smaller; in
calm markets, positions are larger. This is the "Kelly-lite" approach used by
professional quant traders.

**Formula:**
```
position_size = (equity × risk_pct) / ATR
```

**Example:** With $10,000 equity, 1% risk, and ATR of $500:
```
position_size = (10000 × 0.01) / 500 = 0.02 BTC
```

---

## Configuration Reference

### Core Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--exchange` | `binance` | CCXT exchange id |
| `--symbol` | `BTC/USDT` | Market pair |
| `--timeframe` | `1h` | Candle period |
| `--short-window` | `50` | Short moving-average period |
| `--long-window` | `200` | Long moving-average period |
| `--order-amount` | `0.001` | Base-asset trade size |
| `--poll-seconds` | `0` | Seconds between cycles (0 = run once) |

### Risk Controls

| Flag | Default | Description |
|------|---------|-------------|
| `--stop-loss` | `0.01` | Fixed stop-loss fraction |
| `--take-profit` | `0.02` | Fixed take-profit fraction |
| `--use-atr-stops` | off | Use ATR-based SL/TP |
| `--atr-sl-multiplier` | `2.0` | ATR multiples for stop-loss |
| `--atr-tp-multiplier` | `3.0` | ATR multiples for take-profit |
| `--use-trailing-stop` | off | Enable trailing stop |
| `--trail-atr-multiplier` | `2.0` | Trailing stop ATR distance |
| `--max-hold` | none | Max position hold time (e.g. `4h`) |
| `--max-drawdown` | `0.0` | Max drawdown fraction before stopping (0 = disabled) |
| `--max-daily-loss` | `0.0` | Max daily loss fraction (0 = disabled) |
| `--loss-cooldown` | `0` | Seconds to wait after a losing trade |

### Signal Filters

| Flag | Default | Description |
|------|---------|-------------|
| `--confluence-threshold` | `0` | Min confirming indicators to enter (0 = disabled) |
| `--volume-confirmation` | off | Require above-average volume |
| `--rsi-filter` | off | Block entries at RSI extremes |
| `--min-adx` | `0.0` | Min ADX trend strength to enter |
| `--use-xgboost` | off | ML-based signal confirmation |
| `--sell-pressure-ratio` | `1.2` | Order-book pressure threshold |
| `--order-book-depth` | `5` | Number of order-book levels |

### Execution Modes

| Flag | Default | Description |
|------|---------|-------------|
| `--execute` | off | Place real orders (dry-run without this) |
| `--sandbox` | off | Use exchange testnet |
| `--demo` | off | Use Bybit demo environment |
| `--allow-short` | off | Permit short entries |

---

## Recommended Commands

### 1. Conservative Long-Only (Best for Beginners)

Low risk, long-only positions on the 4-hour chart with ATR-based stops and
confluence filtering. Ideal for BTC/USDT in trending markets.

```bash
python3 trader.py \
  --exchange bybit \
  --demo \
  --symbol BTC/USDT \
  --timeframe 4h \
  --short-window 20 \
  --long-window 50 \
  --poll-seconds 60 \
  --use-atr-stops \
  --atr-sl-multiplier 2.0 \
  --atr-tp-multiplier 3.0 \
  --use-trailing-stop \
  --trail-atr-multiplier 2.0 \
  --confluence-threshold 3 \
  --volume-confirmation \
  --rsi-filter \
  --min-adx 25 \
  --max-drawdown 0.05 \
  --loss-cooldown 300 \
  --use-atr-sizing \
  --atr-risk-pct 0.01 \
  --record-file logs/conservative.csv \
  --state-file state/conservative.json
```

**Why this works:**
- 4h timeframe filters noise while catching major trends
- 20/50 MAs are faster than default 50/200 — better for crypto's pace
- Confluence threshold 3 requires 3+ indicators to agree before entry
- ATR-based stops adapt to market volatility automatically
- Trailing stop locks in profits as price advances
- 5% max drawdown protects against black swan events
- 1% risk per trade via ATR sizing ensures survival

---

### 2. Active Swing Trading (Moderate Risk)

For experienced traders targeting more frequent entries on the 1-hour chart.

```bash
python3 trader.py \
  --exchange bybit \
  --demo \
  --symbol BTC/USDT \
  --timeframe 1h \
  --short-window 20 \
  --long-window 50 \
  --poll-seconds 30 \
  --use-atr-stops \
  --atr-sl-multiplier 1.5 \
  --atr-tp-multiplier 3.0 \
  --use-trailing-stop \
  --trail-atr-multiplier 1.5 \
  --confluence-threshold 2 \
  --volume-confirmation \
  --rsi-filter \
  --min-adx 20 \
  --max-drawdown 0.08 \
  --loss-cooldown 120 \
  --use-atr-sizing \
  --atr-risk-pct 0.015 \
  --max-hold 12h \
  --record-file logs/swing.csv \
  --state-file state/swing.json
```

**Why this works:**
- 1h timeframe provides more trade opportunities
- Tighter 1.5 ATR stop but 3 ATR target → 1:2 risk-reward
- Lower confluence threshold (2) = more entries but still filtered
- Max hold of 12 hours prevents holding through major reversals
- 1.5% risk per trade is slightly more aggressive

---

### 3. Altcoin Momentum (Higher Risk, Higher Reward)

For trading high-volatility altcoins like ETH/USDT or SOL/USDT.

```bash
python3 trader.py \
  --exchange bybit \
  --demo \
  --symbol ETH/USDT \
  --timeframe 1h \
  --short-window 12 \
  --long-window 26 \
  --poll-seconds 30 \
  --use-atr-stops \
  --atr-sl-multiplier 2.5 \
  --atr-tp-multiplier 5.0 \
  --use-trailing-stop \
  --trail-atr-multiplier 2.0 \
  --confluence-threshold 2 \
  --volume-confirmation \
  --min-adx 20 \
  --max-drawdown 0.10 \
  --loss-cooldown 180 \
  --use-atr-sizing \
  --atr-risk-pct 0.01 \
  --max-hold 24h \
  --record-file logs/altcoin.csv \
  --state-file state/altcoin.json
```

**Why this works:**
- 12/26 MAs match MACD fast/slow defaults — naturally harmonized signals
- Wider ATR multiples accommodate altcoin volatility
- 1:2 risk-reward ratio (2.5 ATR stop, 5 ATR target)
- 10% max drawdown is generous but prevents total wipeout
- 24h max hold avoids weekend gap risk

---

### 4. ML-Enhanced Trading (Advanced)

Uses XGBoost machine learning for additional signal confirmation.

```bash
python3 trader.py \
  --exchange bybit \
  --demo \
  --symbol BTC/USDT \
  --timeframe 4h \
  --short-window 20 \
  --long-window 50 \
  --poll-seconds 60 \
  --use-xgboost \
  --use-atr-stops \
  --atr-sl-multiplier 2.0 \
  --atr-tp-multiplier 4.0 \
  --use-trailing-stop \
  --trail-atr-multiplier 2.0 \
  --confluence-threshold 2 \
  --volume-confirmation \
  --rsi-filter \
  --min-adx 25 \
  --max-drawdown 0.05 \
  --loss-cooldown 300 \
  --use-atr-sizing \
  --atr-risk-pct 0.01 \
  --record-file logs/ml-enhanced.csv \
  --state-file state/ml-enhanced.json
```

**Why this works:**
- XGBoost model uses 18 features including MACD histogram for prediction
- ML bias adds an independent confirmation layer
- Conservative 2.0/4.0 ATR stops with 1:2 risk-reward
- Confluence threshold of 2 prevents conflicting signals

---

### 5. Live Trading Command (After Demo Validation)

Only use this after running a demo profile for at least 50+ trades with
positive expectancy.

```bash
export TRADER_API_KEY=your_api_key
export TRADER_API_SECRET=your_api_secret

python3 trader.py \
  --exchange bybit \
  --execute \
  --symbol BTC/USDT \
  --timeframe 4h \
  --short-window 20 \
  --long-window 50 \
  --poll-seconds 60 \
  --use-atr-stops \
  --atr-sl-multiplier 2.0 \
  --atr-tp-multiplier 3.0 \
  --use-trailing-stop \
  --trail-atr-multiplier 2.0 \
  --confluence-threshold 3 \
  --volume-confirmation \
  --rsi-filter \
  --min-adx 25 \
  --max-drawdown 0.03 \
  --loss-cooldown 600 \
  --use-atr-sizing \
  --atr-risk-pct 0.005 \
  --record-file logs/live.csv \
  --state-file state/live.json
```

**Key differences from demo:**
- `--max-drawdown 0.03` — tighter 3% drawdown limit
- `--atr-risk-pct 0.005` — risk only 0.5% of equity per trade
- `--loss-cooldown 600` — 10-minute cooldown after losses
- `--confluence-threshold 3` — highest quality entries only

---

## Optimization Tips

### Timeframe Selection

| Timeframe | Best For | Trade Frequency | Noise Level |
|-----------|----------|-----------------|-------------|
| `15m` | Scalping | Very high | High |
| `1h` | Swing trading | Moderate | Moderate |
| `4h` | Position trading | Low | Low |
| `1d` | Long-term trends | Very low | Very low |

**Recommendation:** Start with `4h` for BTC/USDT. Move to `1h` only after
validating on demo with 50+ trades.

### Moving Average Windows

| Setting | Style | Market Condition |
|---------|-------|------------------|
| `12/26` | Aggressive | Strong trending markets |
| `20/50` | Balanced | Most crypto conditions |
| `50/200` | Conservative | Slow trend following |

**Recommendation:** Use `20/50` for most crypto pairs. The default `50/200` is
too slow for crypto market dynamics.

### Risk-Reward Ratios

| SL / TP Multiplier | Ratio | Win Rate Needed |
|---------------------|-------|-----------------|
| `1.5 / 3.0` | 1:2 | 34% |
| `2.0 / 3.0` | 1:1.5 | 40% |
| `2.0 / 4.0` | 1:2 | 34% |
| `2.5 / 5.0` | 1:2 | 34% |

**Recommendation:** Target at least 1:1.5 risk-reward. Higher ratios allow
profitability even with lower win rates.

### Confluence Threshold

| Threshold | Effect |
|-----------|--------|
| `0` | No filtering — all valid signals taken |
| `1` | Light filter — most signals pass |
| `2` | Moderate — recommended starting point |
| `3` | Strict — high-quality entries, fewer trades |
| `4` | Very strict — only the strongest setups |

---

## Backtesting and Validation

### Step 1: Dry-Run Testing

Run the bot in dry-run mode (no `--execute`) to verify it produces sensible
signals:

```bash
python3 trader.py \
  --timeframe 4h \
  --short-window 20 \
  --long-window 50 \
  --poll-seconds 60 \
  --record-file logs/dryrun.csv
```

Review `logs/dryrun.csv` to inspect signal timing, entry/exit prices, and
decision reasons.

### Step 2: Demo Trading

Switch to demo mode with a supported exchange (Bybit) and run for at least
**50 trades** before considering live execution:

```bash
export TRADER_API_KEY=your_demo_key
export TRADER_API_SECRET=your_demo_secret

python3 trader.py \
  --exchange bybit \
  --demo \
  --execute \
  --order-amount 0.001 \
  --timeframe 4h \
  --poll-seconds 60 \
  --record-file logs/demo.csv \
  --state-file state/demo.json
```

### Step 3: Evaluate

After 50+ trades, check:
- **Win rate** > 40% (with 1:1.5+ risk-reward)
- **Profit factor** > 1.5 (total wins / total losses)
- **Max drawdown** < 5%
- **Average trade duration** reasonable for your timeframe
- **No clusters of consecutive losses** > 5

### Step 4: Live with Minimal Risk

Start live trading with the smallest possible position size and the tightest
risk controls. Increase size only after 100+ live trades confirm profitability.

---

## Important Disclaimer

This bot is designed for **educational and experimental purposes**. Cryptocurrency
trading involves significant risk of financial loss.

- **Never risk more than you can afford to lose**
- **Always test on demo/sandbox before using real funds**
- **Past performance does not guarantee future results**
- **Market conditions change** — a profitable strategy today may lose tomorrow
- **Exchange fees, slippage, and funding rates** reduce real-world profits
- **API key security** — never share keys, use IP whitelisting, and limit permissions

The recommended commands above are starting points based on modern trading bot
best practices. You must validate them against current market conditions before
deploying with real capital.
