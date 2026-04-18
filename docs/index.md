# Breakout Trading Strategy Backtest

## Strategy Logic

This project implements a long-only breakout trading strategy using historical daily price data for QQQ. The core idea is that when price closes above its recent rolling high, it may signal the beginning of a new upward trend. A long position is opened at the next trading day’s open after a breakout signal appears.

Once in a trade, the position is closed based on three possible conditions: hitting a profit target, triggering a stop-loss, or reaching a predefined timeout period. To avoid overfitting, I use a rolling walk-forward framework, where approximately one year of data is used for parameter selection, and the following period is used for out-of-sample testing.

---

## Asset Selection

I selected **QQQ** after comparing it with several other highly liquid U.S. assets, including SPY, AAPL, NVDA, and GLD. QQQ showed relatively clean trending behavior, frequent breakout opportunities, and strong liquidity over the sample period, making it a practical choice for this strategy.

---

## Breakout Definition

A breakout is defined as a day when the closing price exceeds the highest closing price observed over the previous *N* trading days.

In the Python implementation, this rule is handled by the function `identify_breakouts(df, lookback)`, which computes a rolling maximum of past closing prices and flags a breakout when the current close exceeds that threshold.

The key parameters are:

- Breakout lookback window: 10, 20, 30, or 55 days  
- Profit target: 5%, 8%, or 10%  
- Stop-loss: 3%, 4%, or 5%  
- Timeout period: 5, 10, or 15 trading days  

---

## Exit Logic

Each trade is closed when one of the following occurs first:

- **Successful:** profit target reached  
- **Stop-loss triggered:** price falls below stop-loss  
- **Timed out:** maximum holding period reached  

---

## Performance Summary

- Number of trades: **10**  
- Average return per trade: **0.01199**  
- Win rate: **0.80**  
- Profit factor: **7.56**  
- Expectancy: **615.10**  
- Max drawdown: **-4.68%**  
- Sharpe ratio: **-0.36**  
- Sortino ratio: **-0.23**  

The strategy achieved a high win rate and strong profit factor, but the negative Sharpe ratio suggests that returns were not stable over time.

---

## Trade Blotter

- [Download Trade Blotter CSV](outputs/blotter.csv)
- [Interactive Trade Table](outputs/trades_table.html)

---

## Trade Outcome Analysis

- [Trade Outcome Histogram](outputs/trade_outcomes.html)
- [Outcome Summary CSV](outputs/outcome_summary.csv)

---

## Equity Curve and Metrics

- [Equity Curve](outputs/equity_curve.html)
- [Metrics CSV](outputs/metrics.csv)
- [Walk-forward Parameter Log](outputs/walkforward_params.csv)

---

## Interpretation

One interesting observation is that all trades in this backtest were classified as "Timed out." This suggests that the chosen profit target and stop-loss levels were not frequently reached within the holding period. In other words, while breakout signals were generated, the price movements were not strong enough to trigger exits based on these thresholds.

This highlights a limitation of the current parameter choices and suggests that further tuning or alternative exit rules may improve performance. Despite this, the project demonstrates a complete workflow for building and evaluating a systematic trading strategy.

---

## Replication Notes

The strategy was implemented in Python using ShinyBroker to retrieve data from Interactive Brokers. The script performs breakout detection, walk-forward backtesting, and exports results to the `outputs` folder.