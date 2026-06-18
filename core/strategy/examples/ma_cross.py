"""双均线交叉策略（Golden Cross / Death Cross）。

买入信号：短期均线上穿长期均线（金叉）
卖出信号：短期均线下穿长期均线（死叉）
"""
from __future__ import annotations

import pandas as pd

from core.strategy.base import BaseStrategy, StrategyParam, registry


@registry.register
class MaCrossStrategy(BaseStrategy):
    name = "双均线交叉"
    description = "短期均线上穿长期均线时买入（金叉），下穿时卖出（死叉）。适合趋势行情。"

    @classmethod
    def params_schema(cls):
        return [
            StrategyParam(
                name="fast_period", label="短期均线周期",
                default=10, param_type="int", min_val=3, max_val=60, step=1,
                description="快线 MA 周期，如 5、10、20",
            ),
            StrategyParam(
                name="slow_period", label="长期均线周期",
                default=30, param_type="int", min_val=10, max_val=250, step=5,
                description="慢线 MA 周期，如 30、60、120",
            ),
        ]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = self.params["fast_period"]
        slow = self.params["slow_period"]

        result = df.copy()
        result["ma_fast"] = result["close"].rolling(fast).mean()
        result["ma_slow"] = result["close"].rolling(slow).mean()

        # 计算信号：当快线从下方穿越慢线 => 买入；从上方穿越 => 卖出
        result["cross"] = result["ma_fast"] - result["ma_slow"]
        result["cross_prev"] = result["cross"].shift(1)

        result["signal"] = 0
        # 金叉（前一日快线 < 慢线，今日快线 >= 慢线）
        result.loc[(result["cross_prev"] < 0) & (result["cross"] >= 0), "signal"] = 1
        # 死叉
        result.loc[(result["cross_prev"] >= 0) & (result["cross"] < 0), "signal"] = -1

        return result.drop(columns=["cross", "cross_prev"])
