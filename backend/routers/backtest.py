"""策略回测路由。"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str = Field("000300", description="股票/指数代码")
    strategy_name: str = Field("双均线交叉", description="策略名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="策略参数")
    start_date: str = Field("", description="开始日期 YYYY-MM-DD")
    end_date: str = Field("", description="结束日期 YYYY-MM-DD")
    initial_capital: float = Field(100000.0, ge=1000, description="初始资金")
    commission_rate: float = Field(0.0003, ge=0, le=0.01, description="手续费率")
    with_benchmark: bool = Field(True, description="是否计算沪深300基准")


@router.get("/strategies")
def list_strategies():
    """列出所有可用策略及参数描述。"""
    import core.strategy.examples  # noqa: F401 触发注册
    from core.strategy.base import registry

    result = []
    for name, cls in registry.all().items():
        schema = cls.params_schema()
        result.append({
            "name": name,
            "description": cls.description,
            "params": [
                {
                    "name": p.name,
                    "label": p.label,
                    "default": p.default,
                    "type": p.param_type,
                    "min": p.min_val,
                    "max": p.max_val,
                    "step": p.step,
                    "options": p.options,
                    "description": p.description,
                }
                for p in schema
            ],
        })
    return {"strategies": result}


@router.post("/run")
def run_backtest(req: BacktestRequest):
    """执行策略回测，返回净值曲线与绩效指标。"""
    import core.strategy.examples  # noqa: F401
    from core.strategy.base import registry
    from core.backtest.engine import BacktestEngine
    from core.data.market import get_market_data

    StrategyCls = registry.get(req.strategy_name)
    if not StrategyCls:
        raise HTTPException(status_code=400, detail=f"策略 '{req.strategy_name}' 不存在")

    md = get_market_data()
    today = datetime.today()
    start = req.start_date or (today - timedelta(days=730)).strftime("%Y-%m-%d")
    end = req.end_date or today.strftime("%Y-%m-%d")

    # 加载行情
    df = md.get_history(req.symbol, start, end, "qfq")
    if df.empty:
        # 尝试当作指数
        df = md.get_index_history(req.symbol, start, end)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {req.symbol} 数据")

    benchmark_df = None
    if req.with_benchmark:
        benchmark_df = md.get_index_history("sh000300", start, end)

    strategy = StrategyCls(**req.params)
    engine = BacktestEngine(req.initial_capital, req.commission_rate)

    try:
        result = engine.run(strategy, df, benchmark_df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测失败: {e}")

    # 序列化净值曲线
    equity_data = [
        {"date": str(d.date()), "equity": round(float(v), 6)}
        for d, v in result.equity_curve.items()
    ]
    benchmark_data = None
    if result.benchmark_curve is not None:
        benchmark_data = [
            {"date": str(d.date()), "value": round(float(v), 6)}
            for d, v in result.benchmark_curve.items()
        ]

    # 信号序列
    df_signals = strategy.generate_signals(df)
    signals = [
        {"date": str(d.date()), "price": round(float(r["close"]), 4), "signal": int(r["signal"])}
        for d, r in df_signals[df_signals["signal"] != 0][["close", "signal"]].iterrows()
    ]

    # 交易记录
    trades = []
    if result.trades is not None and not result.trades.empty:
        for _, row in result.trades.iterrows():
            trades.append({
                "entry_date": str(row.get("entry_date", ""))[:10],
                "exit_date": str(row.get("exit_date", ""))[:10],
                "entry_price": round(float(row.get("entry_price", 0)), 4),
                "exit_price": round(float(row.get("exit_price", 0)), 4),
                "shares": int(row.get("shares", 0)),
                "profit_pct": round(float(row.get("profit_pct", 0)) * 100, 2),
                "profit_amount": round(float(row.get("profit_amount", 0)), 2),
            })

    return {
        "metrics": result.summary(),
        "equity_curve": equity_data,
        "benchmark_curve": benchmark_data,
        "signals": signals,
        "trades": trades,
    }
