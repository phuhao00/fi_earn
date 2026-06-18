"""因子研究页：因子计算、IC 分析、分组回测。"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from scipy import stats

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.market import get_market_data
from app.utils import COLORS

st.set_page_config(page_title="因子研究 | fi_earn", page_icon="🔬", layout="wide")

st.title("🔬 因子研究")
st.caption("计算单只股票的技术类因子，分析因子有效性（IC 分析）与分组收益。")

md = get_market_data()


# ------------------------------------------------------------------ #
# 因子计算函数
# ------------------------------------------------------------------ #
def calc_factor_momentum(close: pd.Series, n: int = 20) -> pd.Series:
    """动量因子：N 日收益率。"""
    return close.pct_change(n)


def calc_factor_reversal(close: pd.Series, n: int = 5) -> pd.Series:
    """反转因子：短期反转（负动量）。"""
    return -close.pct_change(n)


def calc_factor_volatility(close: pd.Series, n: int = 20) -> pd.Series:
    """波动率因子：N 日收益率标准差。"""
    return close.pct_change().rolling(n).std()


def calc_factor_ma_ratio(close: pd.Series, fast: int = 5, slow: int = 20) -> pd.Series:
    """均线比率因子：快线/慢线 - 1，衡量短期趋势。"""
    ma_fast = close.rolling(fast).mean()
    ma_slow = close.rolling(slow).mean()
    return ma_fast / ma_slow - 1


def calc_factor_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI 因子。"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def calc_factor_amount_ratio(close: pd.Series, volume: pd.Series, n: int = 5) -> pd.Series:
    """量价背离因子：短期成交额相对长期的比率。"""
    amount = close * volume
    return amount.rolling(n).mean() / amount.rolling(n * 4).mean() - 1


def calc_factor_turnover(volume: pd.Series, n: int = 10) -> pd.Series:
    """换手率变化因子：N 日平均换手率。"""
    return volume.rolling(n).mean() / volume.rolling(n * 5).mean() - 1


FACTOR_REGISTRY = {
    "动量因子(20日)": lambda df: calc_factor_momentum(df["close"], 20),
    "反转因子(5日)": lambda df: calc_factor_reversal(df["close"], 5),
    "波动率因子(20日)": lambda df: calc_factor_volatility(df["close"], 20),
    "均线比率(5/20)": lambda df: calc_factor_ma_ratio(df["close"], 5, 20),
    "RSI因子(14日)": lambda df: calc_factor_rsi(df["close"], 14),
    "量价背离(5日)": lambda df: calc_factor_amount_ratio(df["close"], df["volume"], 5) if "volume" in df.columns else pd.Series(dtype=float),
    "换手率变化": lambda df: calc_factor_turnover(df["volume"], 10) if "volume" in df.columns else pd.Series(dtype=float),
}


def calc_ic(factor: pd.Series, forward_returns: pd.Series) -> float:
    """计算因子 IC（Pearson 相关系数）。"""
    aligned = pd.concat([factor, forward_returns], axis=1).dropna()
    if len(aligned) < 10:
        return np.nan
    corr, _ = stats.pearsonr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return corr


def calc_rank_ic(factor: pd.Series, forward_returns: pd.Series) -> float:
    """计算因子 Rank IC（Spearman 秩相关系数）。"""
    aligned = pd.concat([factor, forward_returns], axis=1).dropna()
    if len(aligned) < 10:
        return np.nan
    corr, _ = stats.spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return corr


def rolling_ic(factor: pd.Series, returns: pd.Series, window: int = 20) -> pd.Series:
    """滚动 IC 序列。"""
    ic_series = {}
    for i in range(window, len(factor)):
        f_window = factor.iloc[i - window:i]
        r_window = returns.iloc[i - window:i]
        ic_series[factor.index[i]] = calc_rank_ic(f_window, r_window)
    return pd.Series(ic_series)


def group_backtest(factor: pd.Series, forward_returns: pd.Series, n_groups: int = 5) -> pd.DataFrame:
    """
    分组回测：按因子值分成 n_groups 组，计算每组平均收益。
    """
    df = pd.concat([factor, forward_returns], axis=1).dropna()
    df.columns = ["factor", "ret"]
    df["group"] = pd.qcut(df["factor"], n_groups, labels=[f"Q{i+1}" for i in range(n_groups)], duplicates="drop")
    group_ret = df.groupby("group", observed=True)["ret"].mean()
    return group_ret


# ------------------------------------------------------------------ #
# 侧边栏
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header("因子研究设置")

    symbol = st.text_input("股票代码", value="000002", placeholder="如 000002")

    period_opt = st.selectbox("时间范围", ["近1年", "近2年", "近3年"], index=1)
    today = datetime.today()
    days_map = {"近1年": 365, "近2年": 730, "近3年": 1095}
    start_date = (today - timedelta(days=days_map[period_opt])).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    st.markdown("---")
    factor_name = st.selectbox("选择因子", list(FACTOR_REGISTRY.keys()))
    hold_period = st.slider("持有期（天）", 1, 30, 5, help="因子对未来多少天收益进行预测")
    n_groups = st.slider("分组数", 3, 10, 5)
    rolling_window = st.slider("滚动 IC 窗口", 10, 60, 20)

# ------------------------------------------------------------------ #
# 加载数据
# ------------------------------------------------------------------ #
with st.spinner(f"加载 {symbol} 数据..."):
    df = md.get_history(symbol.strip(), start_date, end_date, "qfq")

if df.empty:
    st.error("数据加载失败")
    st.stop()

# ------------------------------------------------------------------ #
# 计算因子与收益
# ------------------------------------------------------------------ #
factor_fn = FACTOR_REGISTRY[factor_name]
factor_vals = factor_fn(df)

# 未来 N 日收益率
forward_ret = df["close"].pct_change(hold_period).shift(-hold_period)

# 剔除无效值
valid_mask = factor_vals.notna() & forward_ret.notna()
factor_clean = factor_vals[valid_mask]
forward_ret_clean = forward_ret[valid_mask]

# ------------------------------------------------------------------ #
# IC 指标
# ------------------------------------------------------------------ #
ic_val = calc_ic(factor_clean, forward_ret_clean)
rank_ic_val = calc_rank_ic(factor_clean, forward_ret_clean)
ic_series = rolling_ic(factor_clean, forward_ret_clean, rolling_window)
icir = ic_series.mean() / ic_series.std() if ic_series.std() > 0 else 0

st.markdown("---")
st.subheader("因子有效性指标")

c1, c2, c3, c4 = st.columns(4)
c1.metric("IC（Pearson）", f"{ic_val:.4f}" if not np.isnan(ic_val) else "N/A",
           "|IC| > 0.05 为有效" if abs(ic_val) > 0.05 else "因子较弱")
c2.metric("Rank IC（Spearman）", f"{rank_ic_val:.4f}" if not np.isnan(rank_ic_val) else "N/A")
c3.metric("IC IR（信息比率）", f"{icir:.2f}")
c4.metric(f"未来{hold_period}日收益预测相关", f"{rank_ic_val*100:.1f}分" if not np.isnan(rank_ic_val) else "N/A",
           "有方向性" if abs(rank_ic_val) > 0.03 else "方向性弱")

# ------------------------------------------------------------------ #
# 滚动 IC 曲线
# ------------------------------------------------------------------ #
st.markdown("---")
col_ic, col_group = st.columns(2)

with col_ic:
    st.subheader(f"滚动 Rank IC（窗口={rolling_window}天）")
    if not ic_series.empty:
        ic_colors = [COLORS["up"] if v >= 0 else COLORS["down"] for v in ic_series.values]
        fig_ic = go.Figure()
        fig_ic.add_trace(go.Bar(
            x=ic_series.index, y=ic_series.values,
            name="Rank IC", marker_color=ic_colors, opacity=0.75,
        ))
        fig_ic.add_hline(y=ic_series.mean(), line_color="#ff9800", line_dash="dash",
                          annotation_text=f"均值 {ic_series.mean():.3f}")
        fig_ic.add_hline(y=0, line_color="white", opacity=0.3)
        fig_ic.update_layout(
            height=320, template="plotly_dark",
            margin=dict(l=40, r=20, t=40, b=20),
            xaxis_title="日期", yaxis_title="IC",
        )
        st.plotly_chart(fig_ic, use_container_width=True)

with col_group:
    st.subheader(f"分组收益（{n_groups} 组，持有{hold_period}天）")
    group_ret = group_backtest(factor_clean, forward_ret_clean, n_groups)
    if not group_ret.empty:
        colors = [COLORS["up"] if v > 0 else COLORS["down"] for v in group_ret.values]
        fig_group = go.Figure(go.Bar(
            x=[str(g) for g in group_ret.index],
            y=group_ret.values * 100,
            marker_color=colors,
            text=[f"{v*100:.2f}%" for v in group_ret.values],
            textposition="outside",
        ))
        fig_group.update_layout(
            height=320, template="plotly_dark",
            margin=dict(l=40, r=20, t=40, b=20),
            xaxis_title="因子分组（Q1=低，Q5=高）",
            yaxis_title=f"平均{hold_period}日收益 (%)",
        )
        st.plotly_chart(fig_group, use_container_width=True)

# ------------------------------------------------------------------ #
# 因子时序图
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("因子值 vs 收盘价")

fig_ts = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.05,
    row_heights=[0.55, 0.45],
    subplot_titles=["收盘价", factor_name],
)
fig_ts.add_trace(
    go.Scatter(x=df.index, y=df["close"], mode="lines", name="收盘价",
               line=dict(color=COLORS["primary"], width=1.5)),
    row=1, col=1,
)
fig_ts.add_trace(
    go.Scatter(x=factor_vals.index, y=factor_vals.values, mode="lines", name=factor_name,
               line=dict(color=COLORS["secondary"], width=1.5),
               fill="tozeroy", fillcolor="rgba(255,152,0,0.1)"),
    row=2, col=1,
)
fig_ts.add_hline(y=0, line_color="white", opacity=0.3, row=2, col=1)
fig_ts.update_layout(
    height=480, template="plotly_dark",
    margin=dict(l=50, r=20, t=40, b=30),
)
st.plotly_chart(fig_ts, use_container_width=True)

# ------------------------------------------------------------------ #
# 因子统计摘要
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("因子统计摘要")

desc = factor_clean.describe()
col_stats = st.columns(6)
for col, (stat_name, val) in zip(col_stats, [
    ("样本数", f"{int(desc['count'])}"),
    ("均值", f"{desc['mean']:.4f}"),
    ("标准差", f"{desc['std']:.4f}"),
    ("最小值", f"{desc['min']:.4f}"),
    ("中位数", f"{desc['50%']:.4f}"),
    ("最大值", f"{desc['max']:.4f}"),
]):
    col.metric(stat_name, val)

# 因子分布直方图
fig_dist = go.Figure(go.Histogram(
    x=factor_clean.values, nbinsx=40,
    marker_color=COLORS["primary"], opacity=0.75, name="因子分布",
))
fig_dist.update_layout(
    title=f"{factor_name} 分布直方图",
    height=280, template="plotly_dark",
    xaxis_title="因子值", yaxis_title="频数",
    margin=dict(l=40, r=20, t=40, b=20),
)
st.plotly_chart(fig_dist, use_container_width=True)

st.markdown("---")
st.caption("IC > 0.05 或 Rank IC > 0.03 通常认为因子具有一定预测能力。ICIR > 0.5 表明因子稳定性较好。")
