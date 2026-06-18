"""因子研究路由。"""
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from scipy import stats

router = APIRouter()


# ------------------------------------------------------------------ #
# 因子计算
# ------------------------------------------------------------------ #

def _calc_factor(df: pd.DataFrame, factor_name: str) -> pd.Series:
    close = df["close"]
    volume = df.get("volume", pd.Series(dtype=float))

    dispatch = {
        "动量因子(20日)": lambda: close.pct_change(20),
        "反转因子(5日)": lambda: -close.pct_change(5),
        "波动率因子(20日)": lambda: close.pct_change().rolling(20).std(),
        "均线比率(5/20)": lambda: close.rolling(5).mean() / close.rolling(20).mean() - 1,
        "RSI因子(14日)": lambda: _rsi(close, 14),
        "量价背离(5日)": lambda: (close * volume).rolling(5).mean() / (close * volume).rolling(20).mean() - 1 if not volume.empty else pd.Series(dtype=float),
        "换手率变化": lambda: volume.rolling(10).mean() / volume.rolling(50).mean() - 1 if not volume.empty else pd.Series(dtype=float),
    }
    fn = dispatch.get(factor_name)
    if fn is None:
        raise ValueError(f"未知因子: {factor_name}")
    return fn()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


@router.get("/factors")
def list_factors():
    """列出所有内置因子名称。"""
    return {
        "factors": [
            "动量因子(20日)",
            "反转因子(5日)",
            "波动率因子(20日)",
            "均线比率(5/20)",
            "RSI因子(14日)",
            "量价背离(5日)",
            "换手率变化",
        ]
    }


@router.get("/calculate")
def calculate_factor(
    symbol: str = Query(..., description="股票代码"),
    factor: str = Query("动量因子(20日)", description="因子名称"),
    hold_period: int = Query(5, ge=1, le=60, description="预测持有期（天）"),
    n_groups: int = Query(5, ge=3, le=10, description="分组数"),
    rolling_window: int = Query(20, ge=10, le=120, description="滚动IC窗口"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """计算因子值、IC 分析、分组回测。"""
    from core.data.market import get_market_data

    md = get_market_data()
    today = datetime.today()
    start = start_date or (today - timedelta(days=730)).strftime("%Y-%m-%d")
    end = end_date or today.strftime("%Y-%m-%d")

    df = md.get_history(symbol, start, end, "qfq")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 数据")

    try:
        factor_vals = _calc_factor(df, factor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    forward_ret = df["close"].pct_change(hold_period).shift(-hold_period)
    valid = factor_vals.notna() & forward_ret.notna()
    fv = factor_vals[valid]
    fr = forward_ret[valid]

    # IC
    ic = float(np.corrcoef(fv.values, fr.values)[0, 1]) if len(fv) > 5 else float("nan")
    rank_ic_val, _ = stats.spearmanr(fv.values, fr.values) if len(fv) > 5 else (float("nan"), None)

    # 滚动 IC
    rolling_ic: list = []
    for i in range(rolling_window, len(fv)):
        f_w = fv.iloc[i - rolling_window:i]
        r_w = fr.iloc[i - rolling_window:i]
        rc, _ = stats.spearmanr(f_w.values, r_w.values)
        rolling_ic.append({"date": str(fv.index[i].date()), "ic": round(float(rc), 4) if not np.isnan(rc) else 0})

    ic_values = [x["ic"] for x in rolling_ic]
    icir = float(np.mean(ic_values) / np.std(ic_values)) if ic_values and np.std(ic_values) > 0 else 0

    # 分组
    group_ret_list = []
    if len(fv) >= n_groups * 3:
        tmp = pd.concat([fv, fr], axis=1)
        tmp.columns = ["factor", "ret"]
        tmp["group"] = pd.qcut(tmp["factor"], n_groups,
                                labels=[f"Q{i+1}" for i in range(n_groups)],
                                duplicates="drop")
        gr = tmp.groupby("group", observed=True)["ret"].mean()
        group_ret_list = [{"group": str(g), "return_pct": round(float(v) * 100, 4)} for g, v in gr.items()]

    # 因子时序（采样 500 点避免过大）
    factor_ts = factor_vals.dropna()
    if len(factor_ts) > 500:
        factor_ts = factor_ts.iloc[::len(factor_ts)//500]
    price_ts = df["close"].reindex(factor_ts.index)

    return {
        "ic": round(ic, 6) if not np.isnan(ic) else None,
        "rank_ic": round(float(rank_ic_val), 6) if rank_ic_val is not None and not np.isnan(rank_ic_val) else None,
        "icir": round(icir, 4),
        "rolling_ic": rolling_ic,
        "group_backtest": group_ret_list,
        "factor_series": [
            {"date": str(d.date()), "value": round(float(v), 6)}
            for d, v in factor_ts.items()
        ],
        "price_series": [
            {"date": str(d.date()), "value": round(float(v), 4)}
            for d, v in price_ts.items()
        ],
        "stats": {
            "count": int(fv.count()),
            "mean": round(float(fv.mean()), 6),
            "std": round(float(fv.std()), 6),
            "min": round(float(fv.min()), 6),
            "median": round(float(fv.median()), 6),
            "max": round(float(fv.max()), 6),
        },
    }
