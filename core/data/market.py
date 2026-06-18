"""
数据获取封装层。

优先通过 OpenBB Platform（openbb-akshare provider）获取数据，
降级方案直接调用 akshare，确保在 OpenBB 未安装时仍可运行。
"""
from __future__ import annotations

import os
import threading
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

        # 后台刷新任务去重：防止同一 key 同时跑多个线程
        self._refreshing: set[str] = set()
        self._refresh_lock = threading.Lock()

    def _bg_refresh(self, cache_key: str, fetch_fn) -> None:
        """在后台守护线程中静默刷新缓存，同一 key 只跑一个并发任务。"""
        with self._refresh_lock:
            if cache_key in self._refreshing:
                return
            self._refreshing.add(cache_key)

        def _run():
            try:
                result = fetch_fn()
                is_empty = result is None or (hasattr(result, "empty") and result.empty) or result == {}
                if not is_empty:
                    cache.set(cache_key, result)
                    logger.info(f"后台刷新完成: {cache_key}")
            except Exception as e:
                logger.warning(f"后台刷新失败 [{cache_key}]: {e}")
            finally:
                with self._refresh_lock:
                    self._refreshing.discard(cache_key)

        threading.Thread(target=_run, daemon=True).start()

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

        # 新鲜缓存：直接返回
        fresh = cache.get(cache_key, ttl_hours=4.0)
        if fresh is not None:
            return fresh

        # 过期但有旧缓存：立刻返回旧数据，后台静默刷新
        stale = cache.get(cache_key, ttl_hours=9999, allow_stale=True)
        if stale is not None:
            self._bg_refresh(cache_key, lambda: self._fetch_history_akshare(symbol, start_date, end_date, adjust))
            return stale

        # 无任何缓存：同步拉取（仅首次）
        df = self._fetch_history_akshare(symbol, start_date, end_date, adjust)
        if not df.empty:
            cache.set(cache_key, df)
        return df

    def _fetch_history_akshare(
        self, symbol: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        """获取日线数据，优先东方财富，失败后降级新浪财经。"""
        pure_code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
        # 新浪财经接口需要 sh/sz 前缀
        if pure_code.startswith("6"):
            sina_code = f"sh{pure_code}"
        else:
            sina_code = f"sz{pure_code}"
        start_ymd = start_date.replace("-", "")
        end_ymd = end_date.replace("-", "")

        # 主接口：东方财富
        try:
            df = self._ak.stock_zh_a_hist(
                symbol=pure_code,
                period="daily",
                start_date=start_ymd,
                end_date=end_ymd,
                adjust=adjust,
            )
            col_map = {
                "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                "收盘": "close", "成交量": "volume", "成交额": "amount",
                "涨跌幅": "pct_chg", "涨跌额": "change", "换手率": "turnover",
            }
            df = df.rename(columns=col_map)
            df["date"] = pd.to_datetime(df["date"])
            return df.set_index("date").sort_index()
        except Exception as e:
            logger.warning(f"东方财富接口失败，降级新浪: {symbol} {e}")

        # 备用接口：新浪财经（不依赖 push2 CDN 节点）
        try:
            df = self._ak.stock_zh_a_daily(
                symbol=sina_code,
                start_date=start_ymd,
                end_date=end_ymd,
                adjust=adjust if adjust in ("qfq", "hfq") else "",
            )
            df["date"] = pd.to_datetime(df["date"])
            return df.set_index("date").sort_index()
        except Exception as e2:
            logger.error(f"新浪财经接口也失败: {symbol} {e2}")
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

        # 主接口：东方财富全量行情
        try:
            df = self._ak.stock_zh_a_spot_em()
            row = df[df["代码"] == pure_code]
            if not row.empty:
                result = row.iloc[0].to_dict()
                cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.warning(f"东方财富实时行情失败，尝试历史数据: {symbol} {e}")

        # 备用：用最新一条历史日线数据充当行情
        try:
            today = datetime.today().strftime("%Y-%m-%d")
            week_ago = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            df2 = self.get_history(symbol, week_ago, today, "qfq")
            if not df2.empty:
                last = df2.iloc[-1]
                result = {
                    "代码": pure_code, "最新价": last.get("close", 0),
                    "涨跌幅": last.get("pct_chg", 0), "成交量": last.get("volume", 0),
                }
                cache.set(cache_key, result)
                return result
        except Exception as e2:
            logger.error(f"备用行情也失败: {symbol} {e2}")
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

        fresh = cache.get(cache_key, ttl_hours=4.0)
        if fresh is not None:
            return fresh

        stale = cache.get(cache_key, ttl_hours=9999, allow_stale=True)
        if stale is not None:
            self._bg_refresh(cache_key, lambda: self._fetch_index_history(index_code, start_date, end_date))
            return stale

        df = self._fetch_index_history(index_code, start_date, end_date)
        if not df.empty:
            cache.set(cache_key, df)
        return df

    def _fetch_index_history(self, index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = pd.DataFrame()
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
        except Exception as e:
            logger.warning(f"东方财富指数接口失败，降级新浪: {index_code} {e}")

        if df.empty:
            try:
                df = self._ak.stock_zh_index_daily(symbol=index_code)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                df = df.loc[
                    (df.index >= pd.to_datetime(start_date)) &
                    (df.index <= pd.to_datetime(end_date))
                ]
            except Exception as e2:
                logger.error(f"新浪财经指数接口也失败: {index_code} {e2}")
        return df

    def get_index_snapshot(self) -> pd.DataFrame:
        """获取主要指数实时快照（用于首页总览）。"""
        fresh = cache.get("index_snapshot", ttl_hours=0.1)
        if fresh is not None:
            return fresh

        stale = cache.get("index_snapshot", ttl_hours=9999, allow_stale=True)
        if stale is not None:
            self._bg_refresh("index_snapshot", self._fetch_index_snapshot)
            return stale

        df = self._fetch_index_snapshot()
        if not df.empty:
            cache.set("index_snapshot", df)
        return df

    def _fetch_index_snapshot(self) -> pd.DataFrame:
        df = pd.DataFrame()
        try:
            df = self._ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        except Exception as e:
            logger.warning(f"东方财富指数快照失败，降级新浪: {e}")

        if df.empty:
            try:
                rows = []
                index_pairs = [
                    ("上证指数", "sh000001"), ("沪深300", "sh000300"),
                    ("深证成指", "sz399001"), ("创业板指", "sz399006"),
                    ("中证500", "sh000905"), ("科创50", "sh000688"),
                ]
                for name, code in index_pairs:
                    try:
                        tmp = self._ak.stock_zh_index_daily(symbol=code)
                        if not tmp.empty:
                            last = tmp.iloc[-1]
                            prev = tmp.iloc[-2] if len(tmp) > 1 else last
                            close = float(last["close"])
                            prev_close = float(prev["close"])
                            chg = round((close - prev_close) / prev_close * 100, 3) if prev_close else 0
                            rows.append({
                                "名称": name, "代码": code,
                                "最新价": close, "涨跌幅": chg,
                                "成交量": last.get("volume", 0),
                            })
                    except Exception:
                        pass
                if rows:
                    df = pd.DataFrame(rows)
            except Exception as e2:
                logger.error(f"新浪指数快照也失败: {e2}")
        return df

    # ------------------------------------------------------------------ #
    # 涨跌幅榜
    # ------------------------------------------------------------------ #

    def get_spot_data(self) -> pd.DataFrame:
        """获取全市场 A 股实时快照（原始 DataFrame），供涨跌榜和选股模块共享。
        TTL 10 分钟，SWR 模式。
        """
        cache_key = "spot_data_raw"
        fresh = cache.get(cache_key, ttl_hours=0.17)  # 10 分钟
        if fresh is not None:
            return fresh

        stale = cache.get(cache_key, ttl_hours=9999, allow_stale=True)
        if stale is not None:
            self._bg_refresh(cache_key, self._fetch_spot_data)
            return stale

        df = self._fetch_spot_data()
        if not df.empty:
            cache.set(cache_key, df)
        return df

    def _fetch_spot_data(self) -> pd.DataFrame:
        """真正拉取全市场快照，带备用接口降级。"""
        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                logger.info(f"全市场快照获取成功: {len(df)} 支")
                return df
        except Exception as e:
            logger.warning(f"stock_zh_a_spot_em 失败: {e}")
        return pd.DataFrame()

    def get_market_movers(self, top_n: int = 10) -> dict[str, pd.DataFrame]:
        """获取涨幅榜和跌幅榜。stale-while-revalidate：有旧数据立刻返回，后台静默刷新。"""
        cache_key = f"movers:{top_n}"
        fresh = cache.get(cache_key, ttl_hours=0.1)
        if fresh is not None:
            return fresh

        stale = cache.get(cache_key, ttl_hours=9999, allow_stale=True)
        if stale is not None:
            self._bg_refresh(cache_key, lambda: self._fetch_market_movers(top_n))
            return stale

        result = self._fetch_market_movers(top_n)
        empty = {"gainers": pd.DataFrame(), "losers": pd.DataFrame()}
        if result["gainers"].empty and result["losers"].empty:
            return empty
        cache.set(cache_key, result)
        return result

    def _fetch_market_movers(self, top_n: int) -> dict[str, pd.DataFrame]:
        # 复用共享快照缓存，避免重复拉取
        df = self.get_spot_data()
        if df is None or df.empty:
            df = None

        if df is None or df.empty:
            try:
                raw = self._ak.stock_board_industry_spot_em()
                col_map = {"板块名称": "名称", "最新价": "最新价", "涨跌幅": "涨跌幅", "板块代码": "代码"}
                raw = raw.rename(columns=col_map)
                raw["成交量"] = raw.get("成交量", pd.Series(dtype=float))
                df = raw[[c for c in ["代码", "名称", "最新价", "涨跌幅", "成交量"] if c in raw.columns]].copy()
            except Exception as e2:
                logger.warning(f"行业板块接口失败，尝试概念板块: {e2}")

        if df is None or df.empty:
            try:
                raw = self._ak.stock_board_concept_spot_em()
                col_map = {"板块名称": "名称", "最新价": "最新价", "涨跌幅": "涨跌幅", "板块代码": "代码"}
                raw = raw.rename(columns=col_map)
                raw["成交量"] = raw.get("成交量", pd.Series(dtype=float))
                df = raw[[c for c in ["代码", "名称", "最新价", "涨跌幅", "成交量"] if c in raw.columns]].copy()
            except Exception as e3:
                logger.error(f"所有行情接口均失败: {e3}")

        if df is None or df.empty:
            return {"gainers": pd.DataFrame(), "losers": pd.DataFrame()}

        try:
            df = df.dropna(subset=["涨跌幅"])
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "成交量"] if c in df.columns]
            gainers = df.nlargest(top_n, "涨跌幅")[cols].reset_index(drop=True)
            losers = df.nsmallest(top_n, "涨跌幅")[cols].reset_index(drop=True)
            return {"gainers": gainers, "losers": losers}
        except Exception as e:
            logger.error(f"处理涨跌幅榜失败: {e}")
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
