"""FastAPI 后端入口。"""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 将项目根目录加入路径，使 core 包可被导入
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.routers import market, backtest, factor

app = FastAPI(
    title="fi_earn API",
    description="A股量化交易研究平台 REST API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/market", tags=["市场数据"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["策略回测"])
app.include_router(factor.router, prefix="/api/factor", tags=["因子研究"])


@app.get("/")
def root():
    return {"status": "ok", "service": "fi_earn API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
