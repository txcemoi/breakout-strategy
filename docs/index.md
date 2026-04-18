# Breakout Trading Strategy Backtest

## Strategy Logic

This project implements a long-only breakout trading strategy using historical daily price data for QQQ. The core idea is that when price closes above its recent rolling high, it may signal the beginning of a new upward trend. A long position is opened at the next trading day’s open after a breakout signal appears. 

Once in a trade, the position is closed based on three possible conditions: hitting a profit target, triggering a stop-loss, or reaching a predefined timeout period. To avoid overfitting, I use a rolling walk-forward framework, where approximately one year of data is used for parameter selection, and the following period is used for out-of-sample testing.

---

## Asset Selection

I selected **QQQ** after comparing it with several other highly liquid U.S. assets that are commonly used in systematic trading, including SPY, AAPL, NVDA, and GLD. I chose QQQ because it showed relatively clean trending behavior, frequent breakout opportunities, and strong liquidity over the sample period. Compared with the alternatives I reviewed, QQQ provided a better balance between tradable signals and realistic execution.

---

## Breakout Definition

A breakout is defined as a day when the closing price exceeds the highest closing price observed over the previous *N* trading days. This is implemented using a rolling maximum of prior closing prices and comparing it to the current close.

In the Python implementation, the breakout rule is handled by the function `identify_breakouts(df, lookback)`. This function calculates the highest closing price over the previous lookback window and flags a breakout whenever the current closing price moves above that threshold. In plain English, it checks whether today’s close is stronger than recent resistance and marks that day as a potential entry signal.

The strategy is long-only, and the key parameters are:

- Breakout lookback window: 10, 20, 30, or 55 days  
- Profit target: 5%, 8%, or 10%  
- Stop-loss: 3%, 4%, or 5%  
- Timeout period: 5, 10, or 15 trading days  

For each training window, the parameter combination with the best in-sample Sharpe ratio is selected and then applied to the next out-of-sample period.

---

## Exit Logic

Each trade is closed when one of the following occurs first:

- **Successful:** the profit target is reached  
- **Stop-loss triggered:** the price drops below the stop-loss threshold  
- **Timed out:** the trade reaches the maximum holding period  

The backtest assumes a fixed position size of 100 shares, includes transaction costs, and uses a 2% annual risk-free rate when calculating risk-adjusted performance metrics.

---

## Performance Summary

The walk-forward backtest produced the following out-of-sample results:

- Number of trades: **10**  
- Average return per trade: **0.01199**  
- Win rate: **0.80**  
- Profit factor: **7.56**  
- Expectancy: **615.10**  
- Max drawdown: **-4.68%**  
- Annualized Sharpe ratio: **-0.36**  
- Annualized Sortino ratio: **-0.23**  
- Risk-free rate assumption: **2%**

The strategy achieved a relatively high win rate and strong profit factor, which means the average winning trade was meaningfully larger than the average losing trade. However, the negative Sharpe and Sortino ratios show that the path of returns was not stable on a day-to-day basis. In other words, the strategy was able to generate profitable trades, but its overall risk-adjusted performance was still weak in this sample.

---

## Trade Blotter

- [Download Trade Blotter CSV](/breakout-strategy/outputs/blotter.csv)

<iframe src="/breakout-strategy/outputs/trades_table.html" width="100%" height="400"></iframe>

---

## Trade Outcome Analysis

<iframe src="/breakout-strategy/outputs/trade_outcomes.html" width="100%" height="500"></iframe>

- [Outcome Summary CSV](/breakout-strategy/outputs/outcome_summary.csv)

---

## Equity Curve and Metrics

<iframe src="/breakout-strategy/outputs/equity_curve.html" width="100%" height="500"></iframe>

- [Metrics CSV](/breakout-strategy/outputs/metrics.csv)  
- [Walk-forward Parameter Log](/breakout-strategy/outputs/walkforward_params.csv)

---

## Replication Notes

The strategy was implemented in Python using ShinyBroker to retrieve historical market data from Interactive Brokers. The script performs breakout detection, applies walk-forward parameter selection, executes the backtest, and outputs trade logs, performance metrics, and visualizations into the `outputs/` directory.

---

## Interpretation

This strategy shows that a simple breakout rule can capture profitable price movements in QQQ. However, the limited number of trades and weak risk-adjusted performance indicate that further refinement is needed. 

Potential improvements include testing additional assets, increasing the sample size, and refining entry and exit rules. Despite these limitations, the project demonstrates a complete workflow for building and evaluating a systematic trading strategy, including data retrieval, signal generation, backtesting, and performance analysis.