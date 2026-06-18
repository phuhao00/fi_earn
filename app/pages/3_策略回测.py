"""策略回测页：策略选择、参数配置、回测执行、结果可视化。"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 导入策略（触发注册）
import core.strategy.examples  # noqa: F401
from core.strategy.base import registry
from core.backtest.engine import BacktestEngine
from core.data.market import get_market_data
from app.utils import equity_curve_chart, drawdown_chart, COLORS

st.set_page_config(page_title="策略回测 | fi_earn", page_icon="🚀", layout="wide")

st.title("🚀 策略回测")

md = get_market_data()

# ------------------------------------------------------------------ #
# 侧边栏：策略 & 参数
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header("回测配置")

    symbol = st.text_input("股票代码", value="000300", placeholder="如 000300 (沪深300)")

    st.markdown("---")
    st.subheader("时间范围")
    today = datetime.today()
    period_opt = st.selectbox("快速选择", ["近1年", "近2年", "近3年", "近5年", "自定义"], index=1)
    days_map = {"近1年": 365, "近2年": 730, "近3年": 1095, "近5年": 1825}
    if period_opt != "自定义":
        start_date = (today - timedelta(days=days_map[period_opt])).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    else:
        start_date = st.date_input("开始日期", today - timedelta(days=730)).strftime("%Y-%m-%d")
        end_date = st.date_input("结束日期", today).strftime("%Y-%m-%d")

    st.markdown("---")
    st.subheader("资金设置")
    initial_capital = st.number_input("初始资金（元）", min_value=10000, max_value=10000000, value=100000, step=10000)
    commission_rate = st.number_input("手续费率", min_value=0.0001, max_value=0.003, value=0.0003, format="%.4f",
                                       help="双边手续费，如 0.0003 = 万分之三")

    st.markdown("---")
    st.subheader("策略选择")
    strategy_names = registry.list_names()
    if not strategy_names:
        st.error("未找到已注册策略")
        st.stop()
    chosen_name = st.selectbox("选择策略", strategy_names)

    StrategyCls = registry.get(chosen_name)
    schema = StrategyCls.params_schema()

    st.markdown("---")
    st.subheader("策略参数")
    strategy_params = {}
    for p in schema:
        if p.param_type == "int":
            strategy_params[p.name] = st.slider(
                p.label, int(p.min_val), int(p.max_val), int(p.default), int(p.step or 1),
                help=p.description,
            )
        elif p.param_type == "float":
            strategy_params[p.name] = st.slider(
                p.label, float(p.min_val), float(p.max_val), float(p.default), float(p.step or 0.1),
                help=p.description,
            )
        elif p.param_type == "select":
            strategy_params[p.name] = st.selectbox(p.label, p.options,
                                                     index=p.options.index(p.default) if p.default in p.options else 0,
                                                     help=p.description)

    run_btn = st.button("▶ 运行回测", type="primary", use_container_width=True)

# ------------------------------------------------------------------ #
# 策略说明
# ------------------------------------------------------------------ #
st.markdown(f"**策略说明**：{StrategyCls.description}")

if not run_btn:
    st.info("请在左侧配置参数，然后点击「运行回测」按钮")
    st.stop()

# ------------------------------------------------------------------ #
# 执行回测
# ------------------------------------------------------------------ #
with st.spinner("加载历史数据..."):
    # 尝试直接用股票历史；如果代码像指数格式则用指数接口
    is_index = symbol.startswith(("sh", "sz", "000", "399", "688"))
    if is_index and len(symbol) <= 6 and not symbol.isdigit():
        df = md.get_index_history(symbol, start_date, end_date)
    else:
        df = md.get_history(symbol, start_date, end_date, "qfq")

    # 基准：沪深300
    benchmark_df = md.get_index_history("sh000300", start_date, end_date)

if df.empty:
    st.error("股票数据加载失败，请检查代码")
    st.stop()

with st.spinner("执行回测中..."):
    strategy = StrategyCls(**strategy_params)
    engine = BacktestEngine(initial_capital=initial_capital, commission_rate=commission_rate)
    try:
        result = engine.run(strategy, df, benchmark_df if not benchmark_df.empty else None)
    except Exception as e:
        st.error(f"回测执行失败: {e}")
        st.stop()

# ------------------------------------------------------------------ #
# 绩效指标卡片
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("绩效概览")

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
metrics = [
    ("总收益率", f"{result.total_return:.2%}", "red" if result.total_return > 0 else "green"),
    ("年化收益率", f"{result.annual_return:.2%}", "red" if result.annual_return > 0 else "green"),
    ("最大回撤", f"{result.max_drawdown:.2%}", "green"),
    ("夏普比率", f"{result.sharpe_ratio:.2f}", "normal"),
    ("卡玛比率", f"{result.calmar_ratio:.2f}", "normal"),
    ("胜率", f"{result.win_rate:.2%}", "normal"),
    ("交易次数", f"{result.trade_count}", "normal"),
]

for col, (label, val, _) in zip([c1, c2, c3, c4, c5, c6, c7], metrics):
    col.metric(label, val)

# ------------------------------------------------------------------ #
# 收益曲线
# ------------------------------------------------------------------ #
st.markdown("---")
col_eq, col_dd = st.columns([2, 1])

with col_eq:
    fig_eq = equity_curve_chart(result, title=f"{chosen_name} | {symbol} 策略净值曲线")
    st.plotly_chart(fig_eq, use_container_width=True)

with col_dd:
    fig_dd = drawdown_chart(result)
    st.plotly_chart(fig_dd, use_container_width=True)

# ------------------------------------------------------------------ #
# 信号标注在 K 线图上
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("交易信号标注")

with st.spinner("生成信号图..."):
    df_signals = strategy.generate_signals(df)

fig_sig = go.Figure()
fig_sig.add_trace(go.Scatter(
    x=df_signals.index, y=df_signals["close"],
    mode="lines", name="收盘价",
    line=dict(color=COLORS["primary"], width=1.5),
))

buy_signals = df_signals[df_signals["signal"] == 1]
sell_signals = df_signals[df_signals["signal"] == -1]

if not buy_signals.empty:
    fig_sig.add_trace(go.Scatter(
        x=buy_signals.index, y=buy_signals["close"],
        mode="markers", name="买入",
        marker=dict(symbol="triangle-up", size=12, color=COLORS["up"]),
    ))
if not sell_signals.empty:
    fig_sig.add_trace(go.Scatter(
        x=sell_signals.index, y=sell_signals["close"],
        mode="markers", name="卖出",
        marker=dict(symbol="triangle-down", size=12, color=COLORS["down"]),
    ))

fig_sig.update_layout(
    height=380, template="plotly_dark",
    xaxis_title="日期", yaxis_title="价格",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=50, r=20, t=40, b=30),
)
st.plotly_chart(fig_sig, use_container_width=True)

# ------------------------------------------------------------------ #
# 交易明细
# ------------------------------------------------------------------ #
st.markdown("---")
st.subheader("交易记录")

if result.trades is not None and not result.trades.empty:
    trades_display = result.trades.copy()
    if "profit_pct" in trades_display.columns:
        trades_display["profit_pct"] = trades_display["profit_pct"].apply(lambda x: f"{x:+.2%}")
    if "profit_amount" in trades_display.columns:
        trades_display["profit_amount"] = trades_display["profit_amount"].apply(lambda x: f"¥{x:+,.2f}")

    rename_map = {
        "entry_date": "买入日期", "exit_date": "卖出日期",
        "entry_price": "买入价", "exit_price": "卖出价",
        "shares": "股数", "profit_pct": "收益率", "profit_amount": "盈亏金额",
    }
    trades_display = trades_display.rename(columns={k: v for k, v in rename_map.items() if k in trades_display.columns})
    st.dataframe(trades_display, use_container_width=True, hide_index=True)

    # 收益分布直方图
    if "profit_pct" not in trades_display.columns and "收益率" in trades_display.columns:
        pass  # 已格式化，跳过
    elif result.trades is not None and "profit_pct" in result.trades.columns:
        fig_hist = go.Figure(go.Histogram(
            x=result.trades["profit_pct"] * 100,
            nbinsx=20,
            marker_color=COLORS["primary"],
            name="收益率分布",
        ))
        fig_hist.add_vline(x=0, line_color="white", line_dash="dash")
        fig_hist.update_layout(
            title="单笔收益率分布",
            height=300, template="plotly_dark",
            xaxis_title="收益率 (%)", yaxis_title="次数",
            margin=dict(l=50, r=20, t=40, b=30),
        )
        st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("该时间段内无成交记录（信号不足或参数不匹配）")
