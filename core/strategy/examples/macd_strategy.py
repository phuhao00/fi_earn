"""MACD 策略。

MACD 线（DIF）上穿信号线（DEA）时买入，下穿时卖出。
同时可选择只在 MACD 柱（HIST）由负转正时买入（更保守）。
"""
from __future__ import annotations

import pandas as pd

from core.strategy.base import BaseStrategy, StrategyParam, registry


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


@registry.register
class MacdStrategy(BaseStrategy):
    name = "MACD 策略"
    description = "DIF 线上穿 DEA 信号线时买入，下穿时卖出。经典趋势跟踪策略。"

    @classmethod
    def params_schema(cls):
        return [
            StrategyParam(
                name="fast_period", label="快线 EMA 周期",
                default=12, param_type="int", min_val=5, max_val=30, step=1,
            ),
            StrategyParam(
                name="slow_period", label="慢线 EMA 周期",
                default=26, param_type="int", min_val=15, max_val=60, step=1,
            ),
            StrategyParam(
                name="signal_period", label="信号线 EMA 周期",
                default=9, param_type="int", min_val=3, max_val=20, step=1,
            ),
            StrategyParam(
                name="use_hist", label="交叉模式",
                default="DIF 穿 DEA", param_type="select",
                options=["DIF 穿 DEA", "HIST 零轴穿越"],
                description="DIF穿DEA更灵敏；HIST零轴更滞后但可靠",
            ),
        ]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = self.params["fast_period"]
        slow = self.params["slow_period"]
        signal_p = self.params["signal_period"]
        use_hist = self.params["use_hist"] == "HIST 零轴穿越"

        result = df.copy()
        ema_fast = _ema(result["close"], fast)
        ema_slow = _ema(result["close"], slow)

        result["dif"] = ema_fast - ema_slow
        result["dea"] = _ema(result["dif"], signal_p)
        result["hist"] = (result["dif"] - result["dea"]) * 2

        result["signal"] = 0

        if use_hist:
            hist_prev = result["hist"].shift(1)
            result.loc[(hist_prev < 0) & (result["hist"] >= 0), "signal"] = 1
            result.loc[(hist_prev >= 0) & (result["hist"] < 0), "signal"] = -1
        else:
            diff = result["dif"] - result["dea"]
            diff_prev = diff.shift(1)
            result.loc[(diff_prev < 0) & (diff >= 0), "signal"] = 1
            result.loc[(diff_prev >= 0) & (diff < 0), "signal"] = -1

        return result
