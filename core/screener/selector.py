"""
智能选股核心模块。

三步流程：
  1. 宇宙过滤   — 用全市场快照排除垃圾股/高位股（纯内存，< 50ms）
  2. 初步评分   — 四维因子（趋势/安全/基本面/热度），产出 Top 30 候选
  3. 技术精排   — 对 Top 30 并发拉 60 日历史，计算 MA + RSI，最终输出 Top 10
"""
from __future__ import annotations

import concurrent.futures
import threading
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from core.data.cache import cache
from core.data.market import get_market_data

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

CACHE_KEY = "screener:top10"
CACHE_TTL_HOURS = 0.5          # 30 分钟新鲜缓存
CANDIDATES_N = 30              # 进入技术精排的候选数
FINAL_N = 10                   # 最终输出数量
HISTORY_DAYS = 65              # 拉取历史天数（确保 MA60 有数据）
MAX_WORKERS = 8                # 并发历史拉取线程数

# 过滤阈值
MIN_FLOAT_CAP = 30e8           # 流通市值 30 亿
MIN_AMOUNT = 5e7               # 成交额 5000 万
MAX_PE = 80
MAX_GAIN_60D = 80.0            # 60 日涨幅上限，超过视为高位
MAX_TODAY_GAIN = 9.5           # 今日涨幅上限（临近涨停）
MIN_PRICE = 2.0                # 最低股价

# 权重
W_TREND = 0.30
W_SAFETY = 0.25
W_FUND = 0.25
W_HOT = 0.20


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #

def _rsi(close: pd.Series, n: int = 14) -> float:
    """计算最新 RSI 值。"""
    if len(close) < n + 1:
        return 50.0
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - 100 / (1 + rs)
    val = rsi_series.dropna()
    return float(val.iloc[-1]) if not val.empty else 50.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalize(series: pd.Series, lo: float = 0.0, hi: float = 100.0) -> pd.Series:
    """Min-max 归一化到 [lo, hi]。"""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([(lo + hi) / 2] * len(series), index=series.index)
    return (series - mn) / (mx - mn) * (hi - lo) + lo


# --------------------------------------------------------------------------- #
# StockSelector
# --------------------------------------------------------------------------- #

class StockSelector:
    """全市场智能选股器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refreshing = False

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def select(self, force: bool = False) -> dict:
        """
        返回选股结果字典 {stocks: [...], error: str|None, from_cache: bool}。

        force=True 时跳过缓存强制重算。
        SWR 模式：有旧缓存时立刻返回，后台静默刷新。
        """
        if not force:
            fresh = cache.get(CACHE_KEY, ttl_hours=CACHE_TTL_HOURS)
            if fresh is not None:
                return {"stocks": fresh, "error": None, "from_cache": True}

            stale = cache.get(CACHE_KEY, ttl_hours=9999, allow_stale=True)
            if stale is not None:
                self._bg_refresh()
                return {"stocks": stale, "error": None, "from_cache": True, "stale": True}

        try:
            result = self._run_pipeline()
        except Exception as e:
            logger.error(f"选股流程异常: {e}", exc_info=True)
            return {"stocks": [], "error": str(e), "from_cache": False}

        if result:
            cache.set(CACHE_KEY, result)
            return {"stocks": result, "error": None, "from_cache": False}
        return {"stocks": [], "error": "筛选后无结果（市场可能已收盘或数据暂不可用）", "from_cache": False}

    # ------------------------------------------------------------------ #
    # 后台刷新
    # ------------------------------------------------------------------ #

    def _bg_refresh(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def _run():
            try:
                result = self._run_pipeline()
                if result:
                    cache.set(CACHE_KEY, result)
                    logger.info(f"选股后台刷新完成: {len(result)} 支")
                else:
                    logger.warning("选股后台刷新：结果为空")
            except Exception as e:
                logger.warning(f"选股后台刷新失败: {e}")
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #

    def _run_pipeline(self) -> list[dict]:
        md = get_market_data()

        # Step 1: 全市场快照 —— 复用 market 模块共享缓存
        logger.info("选股 Step 1: 拉取全市场快照...")
        spot_df = self._fetch_spot(md)
        if spot_df.empty:
            logger.error("全市场快照为空，选股终止")
            return []
        logger.info(f"快照获取 {len(spot_df)} 支股票，列名: {spot_df.columns.tolist()}")

        # 热度数据（新闻代理）
        hot_codes = self._fetch_hot_codes(md)
        logger.info(f"人气榜获取 {len(hot_codes)} 支")

        # Step 2: 宇宙过滤 + 初步评分
        logger.info("选股 Step 2: 宇宙过滤 + 初步评分...")
        scored = self._filter_and_score(spot_df, hot_codes)
        if scored.empty:
            logger.warning("过滤后无候选股票，请检查 API 列名或放宽过滤条件")
            return []

        candidates = scored.nlargest(CANDIDATES_N, "prelim_score")
        logger.info(f"候选股票 {len(candidates)} 支，进入技术精排")

        # Step 3: 技术精排
        logger.info("选股 Step 3: 技术精排（并发拉历史）...")
        final = self._technical_refinement(md, candidates)
        logger.info(f"选股完成，输出 {len(final)} 支")
        return final

    # ------------------------------------------------------------------ #
    # Step 1 数据获取
    # ------------------------------------------------------------------ #

    def _fetch_spot(self, md) -> pd.DataFrame:
        """复用 market 模块的共享快照缓存，避免重复拉取。"""
        try:
            df = md.get_spot_data()
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"md.get_spot_data() 失败，直接拉取: {e}")

        # 降级：直接调用 AkShare
        try:
            df = md._ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.error(f"获取全市场快照失败: {e}")
        return pd.DataFrame()

    def _fetch_hot_codes(self, md) -> dict[str, int]:
        """东方财富人气榜 Top 50，返回 {纯数字代码: 排名}。"""
        try:
            ak = md._ak
            df = ak.stock_hot_rank_em()
            if df.empty:
                return {}
            code_col = next((c for c in df.columns if "代码" in c or "symbol" in c.lower()), None)
            if code_col is None:
                return {}
            codes = df[code_col].astype(str).str.zfill(6).tolist()
            return {c: i + 1 for i, c in enumerate(codes[:50])}
        except Exception as e:
            logger.warning(f"人气榜获取失败，热度维度将为 0: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Step 2 过滤 + 初步评分
    # ------------------------------------------------------------------ #

    def _filter_and_score(self, df: pd.DataFrame, hot_codes: dict[str, int]) -> pd.DataFrame:
        # 统一列名（兼容东方财富字段）
        col_map = {
            "代码": "code", "名称": "name", "最新价": "price",
            "涨跌幅": "change_pct", "成交额": "amount",
            "流通市值": "float_cap", "市盈率-动态": "pe",
            "市净率": "pb", "60日涨跌幅": "gain_60d",
            "换手率": "turnover",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # 必要列检查
        required = ["code", "name", "price"]
        for col in required:
            if col not in df.columns:
                logger.error(f"快照缺少必要列: {col}，当前列: {df.columns.tolist()}")
                return pd.DataFrame()

        df = df.copy()
        df["code"] = df["code"].astype(str).str.zfill(6)
        total_before = len(df)

        # ── 宇宙过滤 ──────────────────────────────────────────────────────
        # 注意：所有数值比较前必须 fillna 或用 .notna() 防止 NaN 误过滤
        mask = pd.Series([True] * len(df), index=df.index)

        # 排除 ST / 退市
        if "name" in df.columns:
            before = mask.sum()
            mask &= ~df["name"].str.contains("ST|退", case=False, na=False)
            logger.debug(f"  ST过滤: {before} → {mask.sum()}")

        # 最低股价（NaN 视为不合格，排除）
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            before = mask.sum()
            mask &= df["price"].fillna(0) >= MIN_PRICE
            logger.debug(f"  价格过滤: {before} → {mask.sum()}")

        # 流通市值（NaN 表示数据缺失，排除；但如果 float_cap 列完全为 NaN 则跳过）
        if "float_cap" in df.columns:
            df["float_cap"] = pd.to_numeric(df["float_cap"], errors="coerce")
            non_null_rate = df["float_cap"].notna().mean()
            if non_null_rate > 0.1:   # 至少 10% 有值才启用此过滤
                before = mask.sum()
                mask &= df["float_cap"].fillna(0) >= MIN_FLOAT_CAP
                logger.debug(f"  市值过滤: {before} → {mask.sum()} (非空率={non_null_rate:.1%})")

        # 成交额（NaN 表示今日未交易，排除；但列近全空则跳过）
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
            non_null_rate = df["amount"].notna().mean()
            if non_null_rate > 0.1:
                before = mask.sum()
                mask &= df["amount"].fillna(0) >= MIN_AMOUNT
                logger.debug(f"  成交额过滤: {before} → {mask.sum()} (非空率={non_null_rate:.1%})")

        # 市盈率（NaN 或 <= 0 排除；列近全空则跳过）
        if "pe" in df.columns:
            df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
            non_null_rate = (df["pe"].notna() & (df["pe"] > 0)).mean()
            if non_null_rate > 0.1:
                before = mask.sum()
                pe_ok = df["pe"].notna() & (df["pe"] > 0) & (df["pe"] <= MAX_PE)
                mask &= pe_ok
                logger.debug(f"  PE过滤: {before} → {mask.sum()} (有效PE率={non_null_rate:.1%})")

        # 今日涨跌幅（NaN 填 0 处理，避免误过滤）
        if "change_pct" in df.columns:
            df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
            before = mask.sum()
            mask &= df["change_pct"].fillna(0) <= MAX_TODAY_GAIN
            logger.debug(f"  涨停过滤: {before} → {mask.sum()}")

        # 60 日涨幅（NaN 填 0，视为未涨）
        if "gain_60d" in df.columns:
            df["gain_60d"] = pd.to_numeric(df["gain_60d"], errors="coerce").fillna(0)
            before = mask.sum()
            mask &= df["gain_60d"] <= MAX_GAIN_60D
            logger.debug(f"  高位过滤: {before} → {mask.sum()}")

        df = df[mask].copy()
        logger.info(f"宇宙过滤: {total_before} → {len(df)} 支通过")
        if df.empty:
            return df

        # ── 四维初步评分 ──────────────────────────────────────────────────

        # 1. 趋势分（今日涨幅 + 60日适中趋势）
        chg = df.get("change_pct", pd.Series(0, index=df.index)).fillna(0)
        g60 = df.get("gain_60d", pd.Series(0, index=df.index)).fillna(0)
        # 今日小涨（0-5%）最佳，60日中等涨幅（5-40%）最佳
        trend_raw = (
            (chg.clip(0, 5) / 5 * 50) +                         # 今日 0-5% → 0-50分
            (g60.clip(5, 40).sub(5).div(35) * 50)               # 60日 5-40% → 0-50分
        )
        df["trend_score"] = _normalize(trend_raw)

        # 2. 安全位分（60日涨幅越小越安全）
        safety_raw = MAX_GAIN_60D - g60.clip(0, MAX_GAIN_60D)
        df["safety_score"] = _normalize(safety_raw)

        # 3. 基本面分（PE/PB）
        pe = df.get("pe", pd.Series(20, index=df.index)).fillna(20)
        pb = df.get("pb", pd.Series(2, index=df.index)).fillna(2).pipe(pd.to_numeric, errors="coerce").fillna(2)
        # PE 理想区间 5-35，超出线性衰减
        pe_score = np.where(
            (pe >= 5) & (pe <= 35), 100,
            np.where(pe < 5, pe / 5 * 100,
                     np.maximum(0, 100 - (pe - 35) / 45 * 100))
        )
        # PB 理想区间 1-4
        pb_clip = pb.clip(1, 8)
        pb_score = np.where(pb_clip <= 4, 100, np.maximum(0, 100 - (pb_clip - 4) / 4 * 100))
        df["fund_score"] = _normalize(pd.Series(pe_score * 0.6 + pb_score * 0.4, index=df.index))

        # 4. 热度分（人气榜代理新闻热度）
        def _hot_score(code: str) -> float:
            rank = hot_codes.get(code)
            if rank is None:
                return 0.0
            return max(0.0, 100.0 - (rank - 1) * 2.0)   # rank 1 → 100, rank 50 → 2

        df["hot_score"] = df["code"].map(_hot_score).fillna(0)

        # 综合初步评分
        df["prelim_score"] = (
            df["trend_score"] * W_TREND +
            df["safety_score"] * W_SAFETY +
            df["fund_score"] * W_FUND +
            df["hot_score"] * W_HOT
        )

        return df

    # ------------------------------------------------------------------ #
    # Step 3 技术精排
    # ------------------------------------------------------------------ #

    def _technical_refinement(self, md, candidates: pd.DataFrame) -> list[dict]:
        codes = candidates["code"].tolist()
        end_date = datetime.today().strftime("%Y-%m-%d")
        start_date = (datetime.today() - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")

        # 并发拉历史
        history_map: dict[str, pd.DataFrame] = {}

        def _fetch(code: str):
            try:
                df = md.get_history(code, start_date, end_date, "qfq")
                return code, df
            except Exception:
                return code, pd.DataFrame()

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, c): c for c in codes}
            for fut in concurrent.futures.as_completed(futures):
                code, df = fut.result()
                history_map[code] = df

        # 计算技术指标并精排
        results = []
        for _, row in candidates.iterrows():
            code = row["code"]
            hist = history_map.get(code, pd.DataFrame())

            rsi14 = 50.0
            ma_aligned = False
            ma_bonus = 0.0

            if not hist.empty and "close" in hist.columns and len(hist) >= 20:
                close = hist["close"]
                rsi14 = _rsi(close, 14)
                ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else None
                ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
                ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else None

                # 均线多头排列
                if ma5 and ma20 and ma60:
                    ma_aligned = ma5 > ma20 > ma60
                    if ma_aligned:
                        ma_bonus = 20.0
                    elif ma5 > ma20:
                        ma_bonus = 10.0

            # RSI 调整分（健康区间 35-65 → 正分；> 70 → 扣分）
            if rsi14 <= 30:
                rsi_bonus = 5.0
            elif rsi14 <= 65:
                rsi_bonus = 15.0 * (rsi14 - 30) / 35        # 30→0, 65→15
            elif rsi14 <= 70:
                rsi_bonus = 15.0 - (rsi14 - 65) * 3.0       # 65→15, 70→0
            else:
                rsi_bonus = -(rsi14 - 70) * 2.0             # 70+ 线性扣分

            # 最终得分（初步评分 + 技术加成，归一化到 0-100）
            tech_adj = (ma_bonus + rsi_bonus) / 35.0 * 20.0   # 技术加成最多 +20
            total_score = _clamp(row["prelim_score"] + tech_adj, 0.0, 100.0)

            # 分项得分（展示用，四舍五入到1位）
            scores = {
                "trend": round(float(row["trend_score"]), 1),
                "safety": round(float(row["safety_score"]), 1),
                "fundamental": round(float(row["fund_score"]), 1),
                "hotness": round(float(row["hot_score"]), 1),
            }

            # 关键指标
            metrics = {
                "pe": round(float(row.get("pe", 0) or 0), 1),
                "pb": round(float(row.get("pb", 0) or 0), 2),
                "float_cap_yi": round(float(row.get("float_cap", 0) or 0) / 1e8, 1),
                "rsi14": round(rsi14, 1),
                "ma_aligned": ma_aligned,
                "gain_60d": round(float(row.get("gain_60d", 0) or 0), 2),
                "amount_yi": round(float(row.get("amount", 0) or 0) / 1e8, 2),
            }

            reason = _build_reason(scores, metrics, ma_aligned, rsi14)

            results.append({
                "code": code,
                "name": str(row.get("name", "")),
                "price": round(float(row.get("price", 0) or 0), 2),
                "change_pct": round(float(row.get("change_pct", 0) or 0), 2),
                "total_score": round(total_score, 1),
                "scores": scores,
                "metrics": metrics,
                "reason": reason,
            })

        # 按最终得分降序取 Top N
        results.sort(key=lambda x: x["total_score"], reverse=True)
        top = results[:FINAL_N]
        for i, item in enumerate(top):
            item["rank"] = i + 1
        return top


# --------------------------------------------------------------------------- #
# 理由生成
# --------------------------------------------------------------------------- #

def _build_reason(scores: dict, metrics: dict, ma_aligned: bool, rsi14: float) -> str:
    parts = []

    if ma_aligned:
        parts.append("均线多头排列")
    elif scores["trend"] >= 60:
        parts.append("短期趋势向上")

    if rsi14 < 70 and rsi14 > 35:
        parts.append(f"RSI {rsi14:.0f} 处于健康区间")
    elif rsi14 >= 70:
        parts.append(f"RSI {rsi14:.0f} 偏高需注意")

    pe = metrics.get("pe", 0)
    if 5 <= pe <= 35:
        parts.append(f"PE {pe} 估值合理")
    elif pe > 35:
        parts.append(f"PE {pe} 偏高")

    gain_60d = metrics.get("gain_60d", 0)
    if gain_60d < 20:
        parts.append("近60日未过度拉升")
    elif gain_60d < 50:
        parts.append(f"近60日涨幅 {gain_60d:.1f}%，尚在可控区间")

    if scores.get("hotness", 0) >= 50:
        parts.append("市场关注度高")

    if not parts:
        parts.append("综合指标均衡")

    return "，".join(parts)


# --------------------------------------------------------------------------- #
# 全局单例
# --------------------------------------------------------------------------- #

_selector: Optional[StockSelector] = None
_selector_lock = threading.Lock()


def get_selector() -> StockSelector:
    global _selector
    if _selector is None:
        with _selector_lock:
            if _selector is None:
                _selector = StockSelector()
    return _selector
