"""技术分析页：K 线图 + 多技术指标叠加。"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.market import get_market_data
from app.utils import COLORS, MA_COLORS

st.set_page_config(page_title="技术分析 | fi_earn", page_icon="📊", layout="wide")

st.title("📊 技术分析")

md = get_market_data()


# ------------------------------------------------------------------ #
# 指标计算函数
# ------------------------------------------------------------------ #
def calc_ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    dif = calc_ema(close, fast) - calc_ema(close, slow)
    dea = calc_ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist

def calc_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def calc_boll(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower

def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9):
    lowest_low = low.rolling(n).min()
    highest_high = high.rolling(n).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

def calc_atr(high, low, close, n=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def calc_obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


# ------------------------------------------------------------------ #
# 侧边栏
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header("分析设置")

    symbol = st.text_input("股票代码", value="600519", placeholder="如 600519")

    period = st.selectbox("时间周期", ["近3月", "近6月", "近1年", "近2年"], index=2)
    today = datetime.today()
    days_map = {"近3月": 90, "近6月": 180, "近1年": 365, "近2年": 730}
    start = (today - timedelta(days=days_map[period])).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    st.markdown("---")
    st.subheader("均线")
    show_ma = st.checkbox("显示均线", value=True)
    if show_ma:
        ma_periods = st.multiselect("MA 周期", [5, 10, 20, 30, 60, 120, 250], default=[5, 20, 60])
        ma_type = st.radio("均线类型", ["SMA（简单均线）", "EMA（指数均线）"], horizontal=True)
    else:
        ma_periods = []
        ma_type = "SMA（简单均线）"

    show_boll = st.checkbox("布林带 (BOLL)", value=False)
    if show_boll:
        boll_n = st.slider("BOLL 周期", 10, 50, 20)
        boll_k = st.slider("BOLL 标准差倍数", 1.0, 3.0, 2.0, 0.5)

    st.markdown("---")
    st.subheader("副图指标")
    sub_indicator = st.selectbox(
        "副图",
        ["无", "MACD", "RSI", "KDJ", "成交量", "OBV", "ATR"],
    )

    if sub_indicator == "MACD":
        macd_fast = st.slider("MACD 快线", 5, 20, 12)
        macd_slow = st.slider("MACD 慢线", 15, 40, 26)
        macd_sig = st.slider("MACD 信号线", 3, 15, 9)
    elif sub_indicator == "RSI":
        rsi_n = st.slider("RSI 周期", 5, 30, 14)
    elif sub_indicator == "KDJ":
        kdj_n = st.slider("KDJ 周期", 5, 30, 9)
    elif sub_indicator == "ATR":
        atr_n = st.slider("ATR 周期", 5, 30, 14)

# ------------------------------------------------------------------ #
# 加载数据
# ------------------------------------------------------------------ #
with st.spinner(f"加载 {symbol} 数据..."):
    df = md.get_history(symbol.strip(), start, end, "qfq")

if df.empty:
    st.error("数据加载失败，请检查股票代码")
    st.stop()

# ------------------------------------------------------------------ #
# 构建图表
# ------------------------------------------------------------------ #
has_sub = sub_indicator != "无"
rows = 2 if has_sub else 1
row_heights = [0.65, 0.35] if has_sub else [1.0]

fig = make_subplots(
    rows=rows, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=row_heights,
    subplot_titles=["", sub_indicator if has_sub else ""],
)

# K 线
fig.add_trace(
    go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing_line_color=COLORS["up"],
        decreasing_line_color=COLORS["down"],
        name="K线",
    ),
    row=1, col=1,
)

# 均线
if show_ma:
    for p in ma_periods:
        if len(df) >= p:
            if "EMA" in ma_type:
                line = calc_ema(df["close"], p)
                label = f"EMA{p}"
            else:
                line = df["close"].rolling(p).mean()
                label = f"MA{p}"
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=line, mode="lines",
                    name=label,
                    line=dict(color=MA_COLORS.get(p, "#aaa"), width=1.3),
                ),
                row=1, col=1,
            )

# 布林带
if show_boll:
    upper, mid, lower = calc_boll(df["close"], boll_n, boll_k)
    for band, lname, dash in [(upper, "BOLL上轨", "dash"), (mid, "BOLL中轨", "solid"), (lower, "BOLL下轨", "dash")]:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=band, mode="lines", name=lname,
                line=dict(color="#00bcd4", width=1, dash=dash),
            ),
            row=1, col=1,
        )

# 副图
if sub_indicator == "MACD":
    dif, dea, hist = calc_macd(df["close"], macd_fast, macd_slow, macd_sig)
    colors = [COLORS["up"] if v >= 0 else COLORS["down"] for v in hist]
    fig.add_trace(go.Bar(x=df.index, y=hist, name="MACD柱", marker_color=colors, opacity=0.7), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dif, mode="lines", name="DIF", line=dict(color="#ff9800", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dea, mode="lines", name="DEA", line=dict(color="#2196f3", width=1.5)), row=2, col=1)

elif sub_indicator == "RSI":
    rsi = calc_rsi(df["close"], rsi_n)
    fig.add_trace(go.Scatter(x=df.index, y=rsi, mode="lines", name=f"RSI{rsi_n}", line=dict(color="#9c27b0", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)

elif sub_indicator == "KDJ":
    k, d, j = calc_kdj(df["high"], df["low"], df["close"], kdj_n)
    fig.add_trace(go.Scatter(x=df.index, y=k, mode="lines", name="K", line=dict(color="#ff9800", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=d, mode="lines", name="D", line=dict(color="#2196f3", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=j, mode="lines", name="J", line=dict(color="#ef5350", width=1.2)), row=2, col=1)

elif sub_indicator == "成交量" and "volume" in df.columns:
    colors = [COLORS["up"] if df["close"].iloc[i] >= df["open"].iloc[i] else COLORS["down"] for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量", marker_color=colors, opacity=0.7), row=2, col=1)

elif sub_indicator == "OBV" and "volume" in df.columns:
    obv = calc_obv(df["close"], df["volume"])
    fig.add_trace(go.Scatter(x=df.index, y=obv, mode="lines", name="OBV", line=dict(color="#00bcd4", width=1.5)), row=2, col=1)

elif sub_indicator == "ATR":
    atr = calc_atr(df["high"], df["low"], df["close"], atr_n)
    fig.add_trace(go.Scatter(x=df.index, y=atr, mode="lines", name=f"ATR{atr_n}", line=dict(color="#ff5722", width=1.5)), row=2, col=1)

fig.update_layout(
    title=f"{symbol} 技术分析",
    height=620 if has_sub else 480,
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=50, r=20, t=60, b=30),
)

st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ #
# 当前指标数值摘要
# ------------------------------------------------------------------ #
if show_ma and ma_periods:
    st.markdown("##### 当前均线值")
    cols = st.columns(len(ma_periods))
    for i, p in enumerate(ma_periods):
        if len(df) >= p:
            if "EMA" in ma_type:
                val = calc_ema(df["close"], p).iloc[-1]
            else:
                val = df["close"].rolling(p).mean().iloc[-1]
            price_now = df["close"].iloc[-1]
            diff = (price_now / val - 1) * 100
            cols[i].metric(f"{'EMA' if 'EMA' in ma_type else 'MA'}{p}", f"{val:.2f}", f"{diff:+.2f}%")

if sub_indicator == "RSI":
    rsi_val = calc_rsi(df["close"], rsi_n).iloc[-1]
    level = "超买" if rsi_val > 70 else "超卖" if rsi_val < 30 else "中性"
    st.metric(f"RSI({rsi_n})", f"{rsi_val:.1f}", level)

elif sub_indicator == "MACD":
    dif_val, dea_val, hist_val = calc_macd(df["close"], macd_fast, macd_slow, macd_sig)
    c1, c2, c3 = st.columns(3)
    c1.metric("DIF", f"{dif_val.iloc[-1]:.4f}")
    c2.metric("DEA", f"{dea_val.iloc[-1]:.4f}")
    c3.metric("HIST", f"{hist_val.iloc[-1]:.4f}", "多头" if hist_val.iloc[-1] > 0 else "空头")
