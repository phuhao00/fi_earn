"""智能选股路由。"""
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from core.screener.selector import get_selector

router = APIRouter()


@router.get("/top10")
async def get_top10(force: bool = Query(False, description="强制重算，绕过缓存")):
    """
    返回智能选股 Top 10 结果。

    - 默认走 stale-while-revalidate 缓存（30分钟），毫秒级响应。
    - force=true 时强制重算（「重新筛选」按钮触发），耗时约 15-30s。
    """
    selector = get_selector()
    res = await run_in_threadpool(selector.select, force)
    stocks = res.get("stocks", [])
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(stocks),
        "stocks": stocks,
        "error": res.get("error"),
        "from_cache": res.get("from_cache", False),
        "stale": res.get("stale", False),
    }
