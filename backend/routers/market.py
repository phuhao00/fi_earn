"""市场数据路由。"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from core.data.market import get_market_data

router = APIRouter()


def _df_to_records(df):
    if df is None or df.empty:
        return []
    df2 = df.reset_index()
    for col in df2.columns:
        if hasattr(df2[col], "dt"):
            df2[col] = df2[col].astype(str)
    return df2.to_dict(orient="records")


@router.get("/history")
async def get_history(
    symbol: str = Query(..., description="股票代码，如 000002"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    adjust: str = Query("qfq", description="复权方式：qfq/hfq/''"),
):
    """获取股票日线历史行情。"""
    md = get_market_data()
    if not end_date:
        end_date = datetime.today().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

    df = await run_in_threadpool(md.get_history, symbol, start_date, end_date, adjust)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 的行情数据")
    return {"symbol": symbol, "data": _df_to_records(df)}


@router.get("/quote")
async def get_quote(symbol: str = Query(..., description="股票代码")):
    """获取实时行情快照。"""
    md = get_market_data()
    quote = await run_in_threadpool(md.get_realtime_quote, symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 实时行情")
    return {"symbol": symbol, "quote": quote}


@router.get("/stocks")
async def get_stocks():
    """获取全量 A 股列表。"""
    md = get_market_data()
    df = await run_in_threadpool(md.get_stock_list)
    return {"data": df.to_dict(orient="records")}


@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1, description="搜索关键词")):
    """按代码或名称搜索股票。"""
    md = get_market_data()
    df = await run_in_threadpool(md.search_stock, q)
    return {"results": df.head(20).to_dict(orient="records")}


@router.get("/index/history")
async def get_index_history(
    code: str = Query("sh000300", description="指数代码，如 sh000300"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取指数历史行情。"""
    md = get_market_data()
    if not end_date:
        end_date = datetime.today().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

    df = await run_in_threadpool(md.get_index_history, code, start_date, end_date)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到指数 {code} 数据")
    return {"code": code, "data": _df_to_records(df)}


@router.get("/index/snapshot")
async def get_index_snapshot():
    """获取主要指数实时快照。"""
    md = get_market_data()
    df = await run_in_threadpool(md.get_index_snapshot)
    if df.empty:
        return {"data": []}
    return {"data": df.to_dict(orient="records")}


@router.get("/movers")
async def get_movers(top_n: int = Query(10, ge=5, le=50)):
    """获取涨跌幅榜。"""
    md = get_market_data()
    movers = await run_in_threadpool(md.get_market_movers, top_n)
    return {
        "gainers": movers["gainers"].to_dict(orient="records"),
        "losers": movers["losers"].to_dict(orient="records"),
    }
