import os
import math
import json
from itertools import product

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import shinybroker as sb


# =========================
# Configuration
# =========================
SYMBOL = "QQQ"
SEC_TYPE = "STK"
EXCHANGE = "SMART"
CURRENCY = "USD"

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 9999

# Pull at least two years; use 3 Y to be safe.
DURATION_STR = "3 Y"
BAR_SIZE = "1 day"
WHAT_TO_SHOW = "TRADES"
USE_RTH = True
TIMEOUT = 10

# Walk-forward structure
TRAIN_DAYS = 252          # ~1 trading year
TEST_DAYS = 63            # ~1 quarter
STEP_DAYS = 63            # roll forward by one quarter

# Parameter grid
BREAKOUT_LOOKBACKS = [10, 20, 30, 55]
PROFIT_TARGETS = [0.05, 0.08, 0.10]
STOP_LOSSES = [0.03, 0.04, 0.05]
TIMEOUTS = [5, 10, 15]

# Portfolio assumptions
INITIAL_CAPITAL = 100000.0
POSITION_SIZE = 100       # shares per trade
RISK_FREE_RATE = 0.02     # annualized assumption
SLIPPAGE_PER_SHARE = 0.01
COMMISSION_PER_TRADE = 1.00

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# Data Fetch
# =========================
def fetch_daily_data(symbol: str) -> pd.DataFrame:
    """
    Fetch daily historical data from ShinyBroker / IBKR.
    Returns a cleaned DataFrame with timestamp, open, high, low, close, volume.
    """
    contract = sb.Contract({
        "symbol": symbol,
        "secType": SEC_TYPE,
        "exchange": EXCHANGE,
        "currency": CURRENCY,
    })

    raw = sb.fetch_historical_data(
        contract=contract,
        endDateTime="",
        durationStr=DURATION_STR,
        barSizeSetting=BAR_SIZE,
        whatToShow=WHAT_TO_SHOW,
        useRTH=USE_RTH,
        host=HOST,
        port=PORT,
        client_id=CLIENT_ID,
        timeout=TIMEOUT,
    )

    if raw is None:
        raise ValueError("Historical data request returned None. Check TWS/IB Gateway and timeout.")
    if isinstance(raw, str):
        raise ValueError(f"Historical data request returned an error string: {raw}")
    if "hst_dta" not in raw:
        raise ValueError("Unexpected ShinyBroker response structure: missing 'hst_dta'.")

    df = raw["hst_dta"].copy()

    # Normalize columns if needed
    expected_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # daily returns
    df["ret"] = df["close"].pct_change()
    return df


# =========================
# Breakout Detection
# =========================
def identify_breakouts(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Long-only breakout detector.

    A breakout occurs when today's close is greater than the highest close
    over the PREVIOUS `lookback` trading days.

    Parameters
    ----------
    df : DataFrame with at least ['timestamp', 'close']
    lookback : int
        Rolling window length used to define the breakout threshold.

    Returns
    -------
    DataFrame
        Original data plus:
        - rolling_high
        - breakout_signal (1 if breakout, else 0)
    """
    out = df.copy()
    out["rolling_high"] = out["close"].shift(1).rolling(lookback).max()
    out["breakout_signal"] = (out["close"] > out["rolling_high"]).astype(int)
    return out


# =========================
# Backtest Engine
# =========================
def backtest_breakout_strategy(
    df: pd.DataFrame,
    lookback: int,
    profit_target: float,
    stop_loss: float,
    timeout_days: int,
    position_size: int = POSITION_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backtest a long-only breakout strategy on daily data.

    Entry:
        Enter long at next day's open after a breakout signal at today's close.

    Exit:
        Exit at the first of:
        1) profit target hit
        2) stop-loss hit
        3) timeout after `timeout_days`
        4) end of dataset

    Assumptions:
        - one position at a time
        - fixed number of shares
        - simple slippage + commission
    """
    data = identify_breakouts(df, lookback).copy()
    trades = []
    equity_rows = []

    capital = INITIAL_CAPITAL
    in_position = False
    entry_idx = None
    entry_price = None
    entry_date = None

    data = data.reset_index(drop=True)

    for i in range(len(data)):
        row = data.loc[i]
        date = row["timestamp"]

        if not in_position:
            # Mark equity daily when flat
            equity_rows.append({
                "timestamp": date,
                "nav": capital,
                "in_position": 0
            })

            # enter at next day's open if breakout today
            if row["breakout_signal"] == 1 and i + 1 < len(data):
                nxt = data.loc[i + 1]
                entry_idx = i + 1
                entry_date = nxt["timestamp"]
                entry_price = nxt["open"] + SLIPPAGE_PER_SHARE
                in_position = True
            continue

        # While in position, evaluate exits on current bar
        bars_held = i - entry_idx + 1
        high_ret = (row["high"] - entry_price) / entry_price
        low_ret = (row["low"] - entry_price) / entry_price
        close_ret = (row["close"] - entry_price) / entry_price

        exit_flag = False
        outcome = None
        exit_price = None
        exit_date = None

        # Profit target
        if high_ret >= profit_target:
            exit_price = entry_price * (1 + profit_target) - SLIPPAGE_PER_SHARE
            exit_date = date
            outcome = "Successful"
            exit_flag = True

        # Stop-loss
        elif low_ret <= -stop_loss:
            exit_price = entry_price * (1 - stop_loss) - SLIPPAGE_PER_SHARE
            exit_date = date
            outcome = "Stop-loss triggered"
            exit_flag = True

        # Timeout
        elif bars_held >= timeout_days:
            exit_price = row["close"] - SLIPPAGE_PER_SHARE
            exit_date = date
            outcome = "Timed out"
            exit_flag = True

        # MTM equity
        mtm_nav = capital + (row["close"] - entry_price) * position_size
        equity_rows.append({
            "timestamp": date,
            "nav": mtm_nav,
            "in_position": 1
        })

        if exit_flag:
            gross_pnl = (exit_price - entry_price) * position_size
            net_pnl = gross_pnl - 2 * COMMISSION_PER_TRADE
            trade_return = net_pnl / (entry_price * position_size)

            capital += net_pnl

            trades.append({
                "entry_timestamp": entry_date,
                "exit_timestamp": exit_date,
                "entry_price": round(entry_price, 4),
                "exit_price": round(exit_price, 4),
                "position_size": position_size,
                "direction": "Long",
                "bars_held": bars_held,
                "gross_pnl": round(gross_pnl, 2),
                "net_pnl": round(net_pnl, 2),
                "trade_return": round(trade_return, 6),
                "outcome": outcome,
                "lookback": lookback,
                "profit_target": profit_target,
                "stop_loss": stop_loss,
                "timeout_days": timeout_days
            })

            in_position = False
            entry_idx = None
            entry_price = None
            entry_date = None

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows)

    if not equity_df.empty:
        equity_df = equity_df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        equity_df["daily_return"] = equity_df["nav"].pct_change().fillna(0.0)

    return trades_df, equity_df


# =========================
# Metrics
# =========================
def compute_performance_metrics(trades_df: pd.DataFrame, equity_df: pd.DataFrame) -> dict:
    metrics = {}

    if trades_df.empty:
        return {
            "num_trades": 0,
            "average_return_per_trade": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio_annualized": 0.0,
            "sortino_ratio_annualized": 0.0,
            "risk_free_rate_assumption": RISK_FREE_RATE,
        }

    metrics["num_trades"] = int(len(trades_df))
    metrics["average_return_per_trade"] = float(trades_df["trade_return"].mean())
    metrics["win_rate"] = float((trades_df["net_pnl"] > 0).mean())

    gross_profit = trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"].sum()
    gross_loss = -trades_df.loc[trades_df["net_pnl"] < 0, "net_pnl"].sum()
    metrics["profit_factor"] = float(gross_profit / gross_loss) if gross_loss > 0 else np.nan
    metrics["expectancy"] = float(trades_df["net_pnl"].mean())

    # drawdown from equity curve
    eq = equity_df.copy()
    eq["cummax"] = eq["nav"].cummax()
    eq["drawdown"] = eq["nav"] / eq["cummax"] - 1
    metrics["max_drawdown"] = float(eq["drawdown"].min()) if not eq.empty else 0.0

    # Sharpe / Sortino from daily NAV returns
    daily = equity_df["daily_return"].dropna()
    if len(daily) > 1 and daily.std() > 0:
        rf_daily = RISK_FREE_RATE / 252
        excess = daily - rf_daily
        metrics["sharpe_ratio_annualized"] = float((excess.mean() / excess.std()) * math.sqrt(252))
    else:
        metrics["sharpe_ratio_annualized"] = 0.0

    downside = daily[daily < 0]
    if len(downside) > 1 and downside.std() > 0:
        rf_daily = RISK_FREE_RATE / 252
        excess = daily - rf_daily
        metrics["sortino_ratio_annualized"] = float((excess.mean() / downside.std()) * math.sqrt(252))
    else:
        metrics["sortino_ratio_annualized"] = 0.0

    metrics["risk_free_rate_assumption"] = RISK_FREE_RATE
    return metrics


# =========================
# Walk-Forward Optimization
# =========================
def select_best_params(train_df: pd.DataFrame) -> dict:
    """
    Grid search on the training window.
    Objective: highest annualized Sharpe ratio.
    """
    best_score = -np.inf
    best_params = None

    for lookback, pt, sl, to in product(
        BREAKOUT_LOOKBACKS, PROFIT_TARGETS, STOP_LOSSES, TIMEOUTS
    ):
        trades_df, equity_df = backtest_breakout_strategy(
            train_df,
            lookback=lookback,
            profit_target=pt,
            stop_loss=sl,
            timeout_days=to,
        )
        metrics = compute_performance_metrics(trades_df, equity_df)
        score = metrics["sharpe_ratio_annualized"]

        # require at least a few trades to avoid silly selections
        if metrics["num_trades"] >= 3 and np.isfinite(score) and score > best_score:
            best_score = score
            best_params = {
                "lookback": lookback,
                "profit_target": pt,
                "stop_loss": sl,
                "timeout_days": to,
                "train_sharpe": score
            }

    if best_params is None:
        best_params = {
            "lookback": 20,
            "profit_target": 0.08,
            "stop_loss": 0.04,
            "timeout_days": 10,
            "train_sharpe": np.nan
        }

    return best_params


def run_walk_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_trades = []
    all_equity = []
    param_log = []

    n = len(df)
    start = 0

    while start + TRAIN_DAYS + TEST_DAYS <= n:
        train_df = df.iloc[start:start + TRAIN_DAYS].copy()
        test_df = df.iloc[start + TRAIN_DAYS:start + TRAIN_DAYS + TEST_DAYS].copy()

        best = select_best_params(train_df)

        test_trades, test_equity = backtest_breakout_strategy(
            test_df,
            lookback=best["lookback"],
            profit_target=best["profit_target"],
            stop_loss=best["stop_loss"],
            timeout_days=best["timeout_days"]
        )

        if not test_trades.empty:
            test_trades["wf_train_start"] = train_df["timestamp"].iloc[0]
            test_trades["wf_train_end"] = train_df["timestamp"].iloc[-1]
            test_trades["wf_test_start"] = test_df["timestamp"].iloc[0]
            test_trades["wf_test_end"] = test_df["timestamp"].iloc[-1]
            all_trades.append(test_trades)

        if not test_equity.empty:
            test_equity["wf_test_start"] = test_df["timestamp"].iloc[0]
            test_equity["wf_test_end"] = test_df["timestamp"].iloc[-1]
            all_equity.append(test_equity)

        param_log.append({
            "train_start": train_df["timestamp"].iloc[0],
            "train_end": train_df["timestamp"].iloc[-1],
            "test_start": test_df["timestamp"].iloc[0],
            "test_end": test_df["timestamp"].iloc[-1],
            **best
        })

        start += STEP_DAYS

    trades_out = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    equity_out = pd.concat(all_equity, ignore_index=True) if all_equity else pd.DataFrame()
    params_out = pd.DataFrame(param_log)

    if not equity_out.empty:
        equity_out = equity_out.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
        equity_out["daily_return"] = equity_out["nav"].pct_change().fillna(0.0)

    return trades_out, equity_out, params_out


# =========================
# Reporting
# =========================
def save_outputs(trades_df: pd.DataFrame, equity_df: pd.DataFrame, metrics: dict):
    trades_df.to_csv(os.path.join(OUTPUT_DIR, "blotter.csv"), index=False)
    equity_df.to_csv(os.path.join(OUTPUT_DIR, "daily_equity.csv"), index=False)

    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, "metrics.csv"), index=False)

    outcome_summary = (
        trades_df["outcome"]
        .value_counts(dropna=False)
        .rename_axis("outcome")
        .reset_index(name="count")
    )
    outcome_summary.to_csv(os.path.join(OUTPUT_DIR, "outcome_summary.csv"), index=False)

    # Equity curve
    if not equity_df.empty:
        fig_eq = px.line(equity_df, x="timestamp", y="nav", title=f"{SYMBOL} Breakout Strategy Equity Curve")
        fig_eq.write_html(os.path.join(OUTPUT_DIR, "equity_curve.html"))

    # Trade outcome histogram
    if not trades_df.empty:
        fig_outcomes = px.histogram(
            trades_df,
            x="outcome",
            title="Trade Outcome Distribution",
            category_orders={"outcome": ["Successful", "Timed out", "Stop-loss triggered"]}
        )
        fig_outcomes.write_html(os.path.join(OUTPUT_DIR, "trade_outcomes.html"))

        # Plotly table
        show_cols = [
            "entry_timestamp", "exit_timestamp", "entry_price", "exit_price",
            "position_size", "direction", "trade_return", "net_pnl", "outcome"
        ]
        table_df = trades_df[show_cols].copy()

        fig_table = go.Figure(data=[go.Table(
            header=dict(values=list(table_df.columns)),
            cells=dict(values=[table_df[c] for c in table_df.columns])
        )])
        fig_table.update_layout(title="Trade Blotter")
        fig_table.write_html(os.path.join(OUTPUT_DIR, "trades_table.html"))

    with open(os.path.join(OUTPUT_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, default=str)


def main():
    df = fetch_daily_data(SYMBOL)

    # Basic cleaning
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    trades_df, equity_df, params_df = run_walk_forward(df)
    params_df.to_csv(os.path.join(OUTPUT_DIR, "walkforward_params.csv"), index=False)

    metrics = compute_performance_metrics(trades_df, equity_df)
    save_outputs(trades_df, equity_df, metrics)

    print("\nDone.")
    print(f"Trades: {len(trades_df)}")
    print(pd.DataFrame([metrics]).T)


if __name__ == "__main__":
    main()