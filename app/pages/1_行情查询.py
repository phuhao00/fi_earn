"""行情查询页：股票搜索 + 交互式 K 线图。"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.market import get_market_data, INDEX_MAP
from app.utils import candlestick_chart, add_ma_traces, COLORS

st.set_page_config(page_title="行情查询 | fi_earn", page_icon="🔍", layout="wide")

st.title("🔍 行情查询")

md = get_market_data()

# ------------------------------------------------------------------ #
# 侧边栏：搜索 & 参数
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header("查询设置")

    mode = st.radio("查询类型", ["股票", "指数"], horizontal=True)

    if mode == "股票":
        query = st.text_input("股票代码/名称", value="000002", placeholder="如 000002 或 万科")
        if query:
            results = md.search_stock(query)
            if not results.empty:
                options = [f"{r['code']} {r['name']}" for _, r in results.head(20).iterrows()]
                selected = st.selectbox("搜索结果", options)
                symbol = selected.split(" ")[0]
            else:
                st.warning("未找到匹配股票")
                symbol = query
        else:
            symbol = "000002"
    else:
        idx_name = st.selectbox("选择指数", list(INDEX_MAP.keys()))
        symbol = INDEX_MAP[idx_name]

    st.markdown("---")
    st.subheader("时间范围")
    period_opt = st.selectbox(
        "快速选择",
        ["近3月", "近6月", "近1年", "近2年", "近3年", "自定义"],
        index=2,
    )
    today = datetime.today()
    if period_opt == "近3月":
        start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    elif period_opt == "近6月":
        start = (today - timedelta(days=180)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    elif period_opt == "近1年":
        start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    elif period_opt == "近2年":
        start = (today - timedelta(days=730)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    elif period_opt == "近3年":
        start = (today - timedelta(days=1095)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    else:
        start = st.date_input("开始日期", value=today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = st.date_input("结束日期", value=today).strftime("%Y-%m-%d")

    st.markdown("---")
    adjust = st.selectbox("复权方式", ["前复权(qfq)", "后复权(hfq)", "不复权"], index=0)
    adjust_map = {"前复权(qfq)": "qfq", "后复权(hfq)": "hfq", "不复权": ""}
    adjust_val = adjust_map[adjust]

    ma_periods = st.multiselect(
        "叠加均线", options=[5, 10, 20, 30, 60, 120, 250],
        default=[5, 20, 60],
    )

# ------------------------------------------------------------------ #
# 加载数据
# ------------------------------------------------------------------ #
with st.spinner(f"加载 {symbol} 行情数据..."):
    if mode == "股票":
        df = md.get_history(symbol, start, end, adjust_val)
    else:
        df = md.get_index_history(symbol, start, end)

if df.empty:
    st.error("数据加载失败，请检查代码或网络连接")
    st.stop()

# ------------------------------------------------------------------ #
# 实时快照（股票模式）
# ------------------------------------------------------------------ #
if mode == "股票":
    quote = md.get_realtime_quote(symbol)
    if quote:
        c1, c2, c3, c4, c5 = st.columns(5)
        price = quote.get("最新价", df["close"].iloc[-1])
        chg_pct = quote.get("涨跌幅", 0)
        chg_pct_f = float(chg_pct) if pd.notna(chg_pct) else 0
        name = quote.get("名称", symbol)

        with c1:
            st.metric("股票", f"{name}（{symbol}）")
        with c2:
            st.metric("最新价", f"¥{float(price):.2f}", f"{chg_pct_f:+.2f}%")
        with c3:
            st.metric("最高", f"¥{float(quote.get('最高', 0)):.2f}")
        with c4:
            st.metric("最低", f"¥{float(quote.get('最低', 0)):.2f}")
        with c5:
            st.metric("成交量", f"{float(quote.get('成交量', 0)):,.0f}手")

# ------------------------------------------------------------------ #
# K 线图
# ------------------------------------------------------------------ #
title = f"{symbol} K 线图 ({start} ~ {end})"
fig = candlestick_chart(df, title=title, height=520, show_volume=True)
if ma_periods:
    fig = add_ma_traces(fig, df, ma_periods)

st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ #
# 行情数据表格
# ------------------------------------------------------------------ #
with st.expander("查看原始数据"):
    display_df = df.copy()
    if "pct_chg" in display_df.columns:
        display_df["pct_chg"] = display_df["pct_chg"].apply(lambda x: f"{x:+.2f}%")
    st.dataframe(display_df.tail(50), use_container_width=True)
    st.download_button(
        "下载 CSV",
        data=df.to_csv().encode("utf-8-sig"),
        file_name=f"{symbol}_{start}_{end}.csv",
        mime="text/csv",
    )

# ------------------------------------------------------------------ #
# 基本统计
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("统计摘要")
close = df["close"]
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("区间最高", f"{df['high'].max():.2f}")
c2.metric("区间最低", f"{df['low'].min():.2f}")
c3.metric("起始价格", f"{close.iloc[0]:.2f}")
c4.metric("最新价格", f"{close.iloc[-1]:.2f}")
chg = (close.iloc[-1] / close.iloc[0] - 1) * 100
c5.metric("区间涨跌幅", f"{chg:+.2f}%")
c6.metric("平均成交量", f"{df['volume'].mean():,.0f}" if "volume" in df.columns else "N/A")
