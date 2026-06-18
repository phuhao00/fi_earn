"""Streamlit 共享工具：图表绘制、样式等。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 让 core 模块可以被 app/ 下的页面 import
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 颜色主题
COLORS = {
    "up": "#ef5350",       # 涨：红
    "down": "#26a69a",     # 跌：绿
    "primary": "#1976d2",  # 主色
    "secondary": "#ff9800",
    "gray": "#757575",
    "bg": "#0e1117",
}

MA_COLORS = {
    5: "#ff9800",
    10: "#2196f3",
    20: "#9c27b0",
    30: "#4caf50",
    60: "#f44336",
    120: "#00bcd4",
    250: "#795548",
}


def candlestick_chart(
    df: pd.DataFrame,
    title: str = "",
    height: int = 480,
    show_volume: bool = True,
) -> go.Figure:
    """绘制 K 线图（含成交量子图）。"""
    rows = 2 if show_volume else 1
    row_heights = [0.7, 0.3] if show_volume else [1.0]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # K 线
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            increasing_line_color=COLORS["up"],
            decreasing_line_color=COLORS["down"],
            name="K线",
        ),
        row=1, col=1,
    )

    # 成交量
    if show_volume and "volume" in df.columns:
        colors = [
            COLORS["up"] if row["close"] >= row["open"] else COLORS["down"]
            for _, row in df.iterrows()
        ]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["volume"],
                marker_color=colors,
                name="成交量",
                opacity=0.7,
            ),
            row=2, col=1,
        )
        fig.update_yaxes(title_text="成交量", row=2, col=1)

    fig.update_layout(
        title=title,
        height=height,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=20, t=50, b=30),
    )
    return fig


def add_ma_traces(fig: go.Figure, df: pd.DataFrame, periods: list[int]) -> go.Figure:
    """在 K 线图上叠加移动均线。"""
    for p in periods:
        if len(df) >= p:
            ma = df["close"].rolling(p).mean()
            color = MA_COLORS.get(p, "#ffffff")
            fig.add_trace(
                go.Scatter(
                    x=df.index, y=ma,
                    mode="lines",
                    name=f"MA{p}",
                    line=dict(color=color, width=1.2),
                ),
                row=1, col=1,
            )
    return fig


def equity_curve_chart(
    result,
    title: str = "策略收益曲线",
    height: int = 420,
) -> go.Figure:
    """绘制回测收益曲线与基准对比图。"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=result.equity_curve.index,
        y=result.equity_curve.values,
        mode="lines",
        name="策略净值",
        line=dict(color=COLORS["primary"], width=2),
        fill="tozeroy",
        fillcolor="rgba(25,118,210,0.1)",
    ))

    if result.benchmark_curve is not None:
        fig.add_trace(go.Scatter(
            x=result.benchmark_curve.index,
            y=result.benchmark_curve.values,
            mode="lines",
            name="基准（沪深300）",
            line=dict(color=COLORS["gray"], width=1.5, dash="dash"),
        ))

    fig.update_layout(
        title=title,
        height=height,
        template="plotly_dark",
        hovermode="x unified",
        xaxis_title="日期",
        yaxis_title="净值",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=20, t=50, b=30),
    )
    return fig


def drawdown_chart(result, height: int = 240) -> go.Figure:
    """绘制回撤曲线。"""
    equity = result.equity_curve
    peak = equity.cummax()
    drawdown = (equity - peak) / peak * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index,
        y=drawdown.values,
        mode="lines",
        name="回撤",
        line=dict(color=COLORS["down"], width=1.5),
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.15)",
    ))
    fig.update_layout(
        title="回撤曲线",
        height=height,
        template="plotly_dark",
        xaxis_title="日期",
        yaxis_title="回撤 (%)",
        margin=dict(l=50, r=20, t=40, b=30),
    )
    return fig


def format_pct(val: float) -> str:
    color = "red" if val > 0 else "green" if val < 0 else "gray"
    sign = "+" if val > 0 else ""
    return f'<span style="color:{color}">{sign}{val:.2f}%</span>'


def metric_card(label: str, value: str, delta: str = "") -> str:
    """返回简单的 HTML 指标卡片。"""
    return f"""
    <div style="background:#1e2127;border-radius:8px;padding:12px 16px;margin:4px;">
        <div style="color:#9e9e9e;font-size:12px">{label}</div>
        <div style="font-size:22px;font-weight:bold;margin:4px 0">{value}</div>
        <div style="font-size:12px">{delta}</div>
    </div>
    """
