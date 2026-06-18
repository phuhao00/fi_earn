"""策略基类与策略注册表。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import pandas as pd


@dataclass
class StrategyParam:
    """策略参数描述符，用于 Streamlit UI 自动生成控件。"""

    name: str
    label: str
    default: Any
    param_type: str  # "int" | "float" | "select"
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    options: Optional[list] = None
    description: str = ""


class BaseStrategy(ABC):
    """
    策略基类。

    子类需实现：
        - params_schema: 返回策略参数描述列表
        - generate_signals: 给定 OHLCV DataFrame，返回带 signal 列的 DataFrame
    """

    name: str = "未命名策略"
    description: str = ""

    def __init__(self, **kwargs):
        self.params: Dict[str, Any] = {}
        schema = self.params_schema()
        for p in schema:
            self.params[p.name] = kwargs.get(p.name, p.default)

    @classmethod
    def params_schema(cls) -> List[StrategyParam]:
        """返回策略参数列表（用于 UI 自动渲染）。"""
        return []

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        根据历史行情生成交易信号。

        Args:
            df: OHLCV DataFrame，index 为日期，必须包含 close 列

        Returns:
            df 副本，新增 signal 列：1=买入，-1=卖出，0=持有
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.params})"


class StrategyRegistry:
    """策略注册表，支持按名称查找和实例化策略。"""

    def __init__(self):
        self._strategies: Dict[str, Type[BaseStrategy]] = {}

    def register(self, cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
        """装饰器：将策略类注册到全局注册表。"""
        self._strategies[cls.name] = cls
        return cls

    def get(self, name: str) -> Optional[Type[BaseStrategy]]:
        return self._strategies.get(name)

    def list_names(self) -> List[str]:
        return list(self._strategies.keys())

    def all(self) -> Dict[str, Type[BaseStrategy]]:
        return dict(self._strategies)


# 全局注册表实例
registry = StrategyRegistry()
