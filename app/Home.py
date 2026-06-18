"""首页：A股市场总览。"""
import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# 将项目根目录加入 Python 路径
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.market import get_market_data, INDEX_MAP
from app.utils import COLORS, format_pct

st.set_page_config(
    page_title="fi_earn | A股量化研究平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义 CSS
st.markdown("""
<style>
    .metric-up { color: #ef5350; font-weight: bold; }
    .metric-down { color: #26a69a; font-weight: bold; }
    .metric-flat { color: #9e9e9e; }
    .section-title { font-size:18px; font-weight:600; margin:16px 0 8px; border-left:4px solid #1976d2; padding-left:8px; }
</style>
""", unsafe_allow_html=True)

st.title("📈 fi_earn · A股量化研究平台")
st.caption("数据源：AkShare（免费）| 回测引擎：AKQuant | 平台：OpenBB")

md = get_market_data()

# ------------------------------------------------------------------ #
# 侧边栏
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header("导航")
    st.info("使用左侧菜单切换功能页面")
    st.markdown("---")
    st.markdown("**数据刷新**")
    if st.button("刷新行情数据", use_container_width=True):
        from core.data.cache import cache
        cache.clear_all()
        st.rerun()
    st.markdown("---")
    st.markdown("**关于**")
    st.markdown("- [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB)")
    st.markdown("- [AkShare](https://github.com/akfamily/akshare)")
    st.markdown("- [AKQuant](https://github.com/akfamily/akquant)")

# ------------------------------------------------------------------ #
# 主要指数快照
# ------------------------------------------------------------------ #
st.markdown('<div class="section-title">主要指数</div>', unsafe_allow_html=True)

index_cols = st.columns(len(INDEX_MAP))
index_snap = md.get_index_snapshot()

for i, (name, code) in enumerate(INDEX_MAP.items()):
    with index_cols[i]:
        if not index_snap.empty:
            # 尝试从快照中找到对应指数
            try:
                row = index_snap[index_snap["代码"].str.contains(code[-6:])]
                if not row.empty:
                    r = row.iloc[0]
                    price = r.get("最新价", r.get("收盘", 0))
                    chg = r.get("涨跌幅", 0)
                    chg_f = float(chg) if pd.notna(chg) else 0
                    delta_str = f"{'+' if chg_f > 0 else ''}{chg_f:.2f}%"
                    st.metric(name, f"{float(price):,.2f}", delta_str)
                else:
                    st.metric(name, "加载中...", "")
            except Exception:
                st.metric(name, "N/A", "")
        else:
            st.metric(name, "获取中...", "")

# ------------------------------------------------------------------ #
# 指数走势图
# ------------------------------------------------------------------ #
st.markdown('<div class="section-title">近期走势（沪深300 / 创业板）</div>', unsafe_allow_html=True)

col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    with st.spinner("加载沪深300走势..."):
        hs300 = md.get_index_history("sh000300", start_date="", end_date="")
        if not hs300.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hs300.index, y=hs300["close"],
                mode="lines", name="沪深300",
                line=dict(color=COLORS["primary"], width=2),
                fill="tozeroy", fillcolor="rgba(25,118,210,0.1)",
            ))
            fig.update_layout(
                title="沪深300 近一年走势",
                height=280, template="plotly_dark",
                margin=dict(l=40, r=20, t=40, b=20),
                xaxis_title="", yaxis_title="点位",
            )
            st.plotly_chart(fig, use_container_width=True)

with col_chart2:
    with st.spinner("加载创业板指走势..."):
        cyb = md.get_index_history("sz399006", start_date="", end_date="")
        if not cyb.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=cyb.index, y=cyb["close"],
                mode="lines", name="创业板指",
                line=dict(color=COLORS["secondary"], width=2),
                fill="tozeroy", fillcolor="rgba(255,152,0,0.1)",
            ))
            fig2.update_layout(
                title="创业板指 近一年走势",
                height=280, template="plotly_dark",
                margin=dict(l=40, r=20, t=40, b=20),
                xaxis_title="", yaxis_title="点位",
            )
            st.plotly_chart(fig2, use_container_width=True)

# ------------------------------------------------------------------ #
# 涨跌幅榜
# ------------------------------------------------------------------ #
st.markdown('<div class="section-title">今日涨跌榜</div>', unsafe_allow_html=True)

with st.spinner("加载涨跌幅榜..."):
    movers = md.get_market_movers(top_n=10)

col_gain, col_lose = st.columns(2)

with col_gain:
    st.markdown("##### 涨幅榜 TOP 10")
    gainers = movers.get("gainers", pd.DataFrame())
    if not gainers.empty:
        display = gainers.copy()
        display.columns = ["代码", "名称", "现价", "涨跌幅(%)", "成交量"]
        display["涨跌幅(%)"] = display["涨跌幅(%)"].apply(lambda x: f"+{x:.2f}%")
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("数据加载中或市场未开盘")

with col_lose:
    st.markdown("##### 跌幅榜 TOP 10")
    losers = movers.get("losers", pd.DataFrame())
    if not losers.empty:
        display = losers.copy()
        display.columns = ["代码", "名称", "现价", "涨跌幅(%)", "成交量"]
        display["涨跌幅(%)"] = display["涨跌幅(%)"].apply(lambda x: f"{x:.2f}%")
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("数据加载中或市场未开盘")

# ------------------------------------------------------------------ #
# 页脚
# ------------------------------------------------------------------ #
st.markdown("---")
st.caption("数据仅供学习研究使用，不构成投资建议。市场有风险，投资需谨慎。")
