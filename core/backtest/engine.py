"""
回测引擎封装。

优先尝试使用 AKQuant（高性能 Rust 内核），
如果 AKQuant 未安装则降级为内置的向量化回测引擎。
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from core.strategy.base import BaseStrategy


@dataclass
class BacktestResult:
    """回测结果容器。"""

    equity_curve: pd.Series          # 每日账户净值（初始=1.0）
    returns: pd.Series                # 每日收益率
    trades: pd.DataFrame              # 交易记录
    benchmark_curve: Optional[pd.Series] = None  # 基准净值

    # 绩效指标
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    calmar_ratio: float = 0.0

    def summary(self) -> dict:
        return {
            "总收益率": f"{self.total_return:.2%}",
            "年化收益率": f"{self.annual_return:.2%}",
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.2f}",
            "卡玛比率": f"{self.calmar_ratio:.2f}",
            "胜率": f"{self.win_rate:.2%}",
            "交易次数": self.trade_count,
        }


def _calc_metrics(equity: pd.Series, returns: pd.Series, trades: pd.DataFrame) -> dict:
    """计算绩效指标。"""
    if equity.empty or len(equity) < 2:
        return {}

    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    n_days = (equity.index[-1] - equity.index[0]).days
    annual_return = (1 + total_return) ** (365 / max(n_days, 1)) - 1

    # 最大回撤
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_drawdown = drawdown.min()

    # 夏普比率（年化，无风险利率 2.5%）
    rf_daily = 0.025 / 252
    excess = returns - rf_daily
    sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    # 卡玛比率
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # 胜率（按笔计算）
    if not trades.empty and "profit_pct" in trades.columns:
        wins = (trades["profit_pct"] > 0).sum()
        win_rate = wins / len(trades) if len(trades) > 0 else 0.0
    else:
        win_rate = 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "calmar_ratio": calmar,
        "win_rate": win_rate,
        "trade_count": len(trades),
    }


def _vectorized_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0003,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """
    向量化回测核心逻辑（纯 pandas/numpy 实现）。

    假设：每次信号全仓操作，T+1 日开盘成交，不考虑涨跌停。
    """
    df = df.copy()
    prices = df["close"].values
    signals = df["signal"].values
    dates = df.index

    n = len(prices)
    cash = initial_capital
    position = 0          # 持有股数
    nav = np.zeros(n)     # 每日账户总值

    trades_list = []
    entry_price = 0.0
    entry_date = None

    for i in range(n):
        price = prices[i]
        sig = signals[i]

        # T+1 成交：今天发出信号，明天开盘价成交
        # 简化为当天收盘价成交（向量化回测常见近似）
        if sig == 1 and position == 0 and cash > 0:
            # 买入：全仓，100股整数倍
            shares = int(cash / (price * (1 + commission_rate)) / 100) * 100
            if shares > 0:
                cost = shares * price * (1 + commission_rate)
                cash -= cost
                position = shares
                entry_price = price
                entry_date = dates[i]

        elif sig == -1 and position > 0:
            # 卖出：全部平仓
            proceeds = position * price * (1 - commission_rate)
            profit_pct = (price - entry_price) / entry_price
            trades_list.append({
                "entry_date": entry_date,
                "exit_date": dates[i],
                "entry_price": entry_price,
                "exit_price": price,
                "shares": position,
                "profit_pct": profit_pct,
                "profit_amount": proceeds - position * entry_price,
            })
            cash += proceeds
            position = 0

        nav[i] = cash + position * price

    # 如果结束时仍持仓，按最后收盘价平仓
    if position > 0:
        last_price = prices[-1]
        trades_list.append({
            "entry_date": entry_date,
            "exit_date": dates[-1],
            "entry_price": entry_price,
            "exit_price": last_price,
            "shares": position,
            "profit_pct": (last_price - entry_price) / entry_price,
            "profit_amount": position * (last_price - entry_price),
        })

    equity = pd.Series(nav / initial_capital, index=dates, name="equity")
    daily_returns = equity.pct_change().fillna(0)
    trades_df = pd.DataFrame(trades_list)

    return equity, daily_returns, trades_df


class BacktestEngine:
    """
    回测引擎。

    优先使用 AKQuant；如未安装则自动降级为内置向量化引擎。
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_rate: float = 0.0003,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self._use_akquant = self._check_akquant()

    def _check_akquant(self) -> bool:
        try:
            import akquant  # noqa: F401
            logger.info("AKQuant 已加载，使用高性能回测引擎")
            return True
        except ImportError:
            logger.info("AKQuant 未安装，使用内置向量化回测引擎")
            return False

    def run(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        benchmark_df: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        执行回测。

        Args:
            strategy: 策略实例
            df: OHLCV DataFrame（index 为日期，必须含 close 列）
            benchmark_df: 基准指数 OHLCV（可选，用于对比）

        Returns:
            BacktestResult 对象
        """
        if df.empty or "close" not in df.columns:
            raise ValueError("DataFrame 为空或缺少 close 列")

        # 生成信号
        logger.info(f"运行策略: {strategy.name} | 参数: {strategy.params}")
        df_signals = strategy.generate_signals(df)

        if "signal" not in df_signals.columns:
            raise ValueError("策略未生成 signal 列")

        # 执行回测
        if self._use_akquant:
            equity, returns, trades = self._run_akquant(df_signals)
        else:
            equity, returns, trades = _vectorized_backtest(
                df_signals, self.initial_capital, self.commission_rate
            )

        # 计算基准曲线
        benchmark_curve = None
        if benchmark_df is not None and not benchmark_df.empty:
            bm_close = benchmark_df["close"].reindex(equity.index, method="ffill")
            benchmark_curve = bm_close / bm_close.iloc[0]
            benchmark_curve.name = "benchmark"

        # 计算绩效指标
        metrics = _calc_metrics(equity, returns, trades)

        return BacktestResult(
            equity_curve=equity,
            returns=returns,
            trades=trades,
            benchmark_curve=benchmark_curve,
            **metrics,
        )

    def _run_akquant(
        self, df: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
        """
        使用 AKQuant run_backtest 执行回测。

        构建一个继承 aq.Strategy 的适配器类，将预计算的信号列注入
        AKQuant 的 on_bar 回调，利用其 Rust 内核进行高性能订单撮合。
        """
        try:
            import akquant as aq

            # 预构建信号字典：date -> signal
            signal_map: dict = {}
            in_pos = False
            for ts, sig in df["signal"].items():
                if sig == 1:
                    in_pos = True
                elif sig == -1:
                    in_pos = False
                signal_map[ts] = 1 if in_pos else 0

            initial_capital = self.initial_capital
            commission_rate = self.commission_rate

            class SignalStrategy(aq.Strategy):
                def on_bar(self, bar):
                    ts = bar.datetime if isinstance(bar.datetime, pd.Timestamp) else pd.Timestamp(bar.datetime)
                    # 找最接近的日期键
                    target = signal_map.get(ts, None)
                    if target is None:
                        ts_date = ts.normalize()
                        target = signal_map.get(ts_date, 0)

                    symbol = bar.symbol
                    has_pos = self.position(symbol) is not None and self.position(symbol).quantity > 0

                    if target == 1 and not has_pos:
                        cash = self.cash
                        price = bar.close
                        if price and price > 0:
                            shares = int(cash * 0.95 / price / 100) * 100
                            if shares > 0:
                                self.buy(symbol, shares)
                    elif target == 0 and has_pos:
                        qty = self.position(symbol).quantity
                        if qty > 0:
                            self.sell(symbol, qty)

            aq_df = df[["open", "high", "low", "close", "volume"]].copy()
            aq_df.index.name = "datetime"

            result = aq.run_backtest(
                data=aq_df,
                strategy=SignalStrategy,
                symbols="STOCK",
                initial_cash=initial_capital,
                commission_rate=commission_rate,
                show_progress=False,
            )

            # 提取净值序列
            metrics = result.performance_metrics if hasattr(result, "performance_metrics") else None
            if hasattr(result, "portfolio_value"):
                equity_raw = result.portfolio_value
            elif hasattr(result, "equity_curve"):
                equity_raw = result.equity_curve
            else:
                raise ValueError("无法从 AKQuant 结果提取净值序列")

            equity = pd.Series(
                equity_raw.values / initial_capital,
                index=pd.to_datetime(equity_raw.index),
                name="equity",
            )
            returns = equity.pct_change().fillna(0)

            trades = pd.DataFrame()
            if hasattr(result, "closed_trades") and result.closed_trades:
                trades = pd.DataFrame([
                    {
                        "entry_date": t.entry_time,
                        "exit_date": t.exit_time,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "shares": t.quantity,
                        "profit_pct": (t.exit_price - t.entry_price) / t.entry_price if t.entry_price else 0,
                        "profit_amount": t.pnl if hasattr(t, "pnl") else 0,
                    }
                    for t in result.closed_trades
                ])

            return equity, returns, trades

        except Exception as e:
            logger.warning(f"AKQuant 回测失败，降级为内置引擎: {e}")
            return _vectorized_backtest(df, self.initial_capital, self.commission_rate)
