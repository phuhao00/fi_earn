"""
数据获取封装层。

优先通过 OpenBB Platform（openbb-akshare provider）获取数据，
降级方案直接调用 akshare，确保在 OpenBB 未安装时仍可运行。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from .cache import cache

# 主要指数代码映射（AkShare 格式）
INDEX_MAP = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "中证1000": "sh000852",
    "科创50": "sh000688",
}

# AkShare 股票代码前缀
def _normalize_symbol(symbol: str) -> str:
    """将纯数字代码补全为 sh/sz 前缀格式（AkShare 历史数据接口用）。"""
    symbol = symbol.strip().upper()
    if symbol.startswith(("SH", "SZ", "sh", "sz")):
        return symbol.lower()
    code = symbol.lstrip("0")
    if symbol.startswith("6"):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _obb_to_df(result) -> pd.DataFrame:
    """将 OpenBB OBBject 转换为 DataFrame 并规范化列名。"""
    df = result.to_dataframe()
    df.columns = [c.lower() for c in df.columns]
    return df


class MarketData:
    """统一的市场数据访问接口。"""

    def __init__(self, use_openbb: bool = True):
        self._use_openbb = use_openbb
        self._obb = None
        if use_openbb:
            try:
                from openbb import obb
                self._obb = obb
                logger.info("OpenBB Platform 已加载")
            except ImportError:
                logger.warning("OpenBB 未安装，降级为直接使用 AkShare")
                self._use_openbb = False

        try:
            import akshare as ak
            self._ak = ak
        except ImportError as e:
            raise RuntimeError("akshare 未安装，请运行: pip install akshare") from e

    # ------------------------------------------------------------------ #
    # 历史行情
    # ------------------------------------------------------------------ #

    def get_history(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取股票日线历史行情。

        Args:
            symbol: 股票代码，如 "000002" 或 "sh600000"
            start_date: 开始日期 "YYYY-MM-DD"，默认近 1 年
            end_date: 结束日期 "YYYY-MM-DD"，默认今天
            adjust: 复权方式，"qfq"=前复权，"hfq"=后复权，""=不复权

        Returns:
            DataFrame，包含 date/open/high/low/close/volume 列
        """
        if not end_date:
            end_date = datetime.today().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

        cache_key = f"history:{symbol}:{start_date}:{end_date}:{adjust}"
        cached = cache.get(cache_key, ttl_hours=4.0)
        if cached is not None:
            return cached

        df = self._fetch_history_akshare(symbol, start_date, end_date, adjust)
        cache.set(cache_key, df)
        return df

    def _fetch_history_akshare(
        self, symbol: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        """直接调用 AkShare 获取日线数据。"""
        # AkShare stock_zh_a_hist 接口：代码不含前缀
        pure_code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
        start_ymd = start_date.replace("-", "")
        end_ymd = end_date.replace("-", "")

        try:
            df = self._ak.stock_zh_a_hist(
                symbol=pure_code,
                period="daily",
                start_date=start_ymd,
                end_date=end_ymd,
                adjust=adjust,
            )
            # 规范化列名
            col_map = {
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "pct_chg",
                "涨跌额": "change",
                "换手率": "turnover",
            }
            df = df.rename(columns=col_map)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            return df
        except Exception as e:
            logger.error(f"AkShare 获取历史行情失败 {symbol}: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # 实时行情
    # ------------------------------------------------------------------ #

    def get_realtime_quote(self, symbol: str) -> dict:
        """获取单只股票实时行情。"""
        cache_key = f"realtime:{symbol}"
        cached = cache.get(cache_key, ttl_hours=0.05)  # 3 分钟缓存
        if cached is not None:
            return cached

        pure_code = symbol.replace("sh", "").replace("sz", "")
        try:
            df = self._ak.stock_zh_a_spot_em()
            row = df[df["代码"] == pure_code]
            if row.empty:
                return {}
            result = row.iloc[0].to_dict()
            cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"获取实时行情失败 {symbol}: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # 股票列表
    # ------------------------------------------------------------------ #

    def get_stock_list(self) -> pd.DataFrame:
        """获取 A 股全量股票列表（代码 + 名称 + 所属交易所）。"""
        cached = cache.get("stock_list", ttl_hours=24.0)
        if cached is not None:
            return cached

        try:
            df = self._ak.stock_info_a_code_name()
            df.columns = ["code", "name"]
            cache.set("stock_list", df)
            return df
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return pd.DataFrame(columns=["code", "name"])

    def search_stock(self, query: str) -> pd.DataFrame:
        """按代码或名称模糊搜索股票。"""
        stocks = self.get_stock_list()
        if stocks.empty:
            return stocks
        q = query.strip()
        mask = stocks["code"].str.contains(q, case=False) | stocks["name"].str.contains(q, case=False)
        return stocks[mask].reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # 指数行情
    # ------------------------------------------------------------------ #

    def get_index_history(
        self,
        index_code: str = "sh000300",
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame:
        """获取指数历史行情。index_code 格式如 'sh000300'。"""
        if not end_date:
            end_date = datetime.today().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

        cache_key = f"index:{index_code}:{start_date}:{end_date}"
        cached = cache.get(cache_key, ttl_hours=4.0)
        if cached is not None:
            return cached

        try:
            df = self._ak.index_zh_a_hist(
                symbol=index_code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
            col_map = {
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume",
            }
            df = df.rename(columns=col_map)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            cache.set(cache_key, df)
            return df
        except Exception as e:
            logger.error(f"获取指数行情失败 {index_code}: {e}")
            return pd.DataFrame()

    def get_index_snapshot(self) -> pd.DataFrame:
        """获取主要指数实时快照（用于首页总览）。"""
        cached = cache.get("index_snapshot", ttl_hours=0.1)
        if cached is not None:
            return cached

        try:
            df = self._ak.stock_zh_index_spot_em(symbol="沪深重要指数")
            cache.set("index_snapshot", df)
            return df
        except Exception as e:
            logger.error(f"获取指数快照失败: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # 涨跌幅榜
    # ------------------------------------------------------------------ #

    def get_market_movers(self, top_n: int = 10) -> dict[str, pd.DataFrame]:
        """获取涨幅榜和跌幅榜（A 股实时）。"""
        cached = cache.get(f"movers:{top_n}", ttl_hours=0.1)
        if cached is not None:
            return cached

        try:
            df = self._ak.stock_zh_a_spot_em()
            df = df.dropna(subset=["涨跌幅"])
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            gainers = df.nlargest(top_n, "涨跌幅")[["代码", "名称", "最新价", "涨跌幅", "成交量"]].reset_index(drop=True)
            losers = df.nsmallest(top_n, "涨跌幅")[["代码", "名称", "最新价", "涨跌幅", "成交量"]].reset_index(drop=True)
            result = {"gainers": gainers, "losers": losers}
            cache.set(f"movers:{top_n}", result)
            return result
        except Exception as e:
            logger.error(f"获取涨跌幅榜失败: {e}")
            return {"gainers": pd.DataFrame(), "losers": pd.DataFrame()}

    # ------------------------------------------------------------------ #
    # 财务数据
    # ------------------------------------------------------------------ #

    def get_financial_indicator(self, symbol: str) -> pd.DataFrame:
        """获取股票财务指标（PE/PB/ROE 等）。"""
        pure_code = symbol.replace("sh", "").replace("sz", "")
        cache_key = f"financial:{pure_code}"
        cached = cache.get(cache_key, ttl_hours=24.0)
        if cached is not None:
            return cached

        try:
            df = self._ak.stock_financial_analysis_indicator(symbol=pure_code, start_year="2020")
            cache.set(cache_key, df)
            return df
        except Exception as e:
            logger.error(f"获取财务指标失败 {symbol}: {e}")
            return pd.DataFrame()


# 全局单例
_market_data: Optional[MarketData] = None


def get_market_data() -> MarketData:
    global _market_data
    if _market_data is None:
        _market_data = MarketData()
    return _market_data
