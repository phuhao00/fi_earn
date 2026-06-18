"""FastAPI 后端入口。"""
import os
import sys
from pathlib import Path

# ── 用 curl_cffi 替换 requests，绕过 TLS 指纹识别 ────────────────────────────
# 东方财富 CDN 会封锁 Python urllib3 的 TLS 指纹，curl_cffi 模拟 Chrome 指纹可正常访问。
# 必须在任何 import akshare / openbb 之前完成替换。
try:
    from curl_cffi.requests import Session as _CffiSession, get as _cffi_get, post as _cffi_post
    import requests as _real_requests

    # 把 curl_cffi Session 包装成 requests 兼容的接口
    class _ChromeSession(_CffiSession):
        """模拟 Chrome TLS 指纹、不走系统代理，兼容 requests.Session 接口。"""

        def __init__(self, *args, **kwargs):
            kwargs.setdefault("impersonate", "chrome110")
            super().__init__(*args, **kwargs)
            # requests.Session 有 mount/adapters 等属性，补全以防 akshare 访问
            self.adapters = {}
            self.hooks = {"response": []}
            self.auth = None
            self.cert = None
            self.verify = True
            self.stream = False
            self.max_redirects = 30

        def mount(self, prefix, adapter):
            self.adapters[prefix] = adapter

        def request(self, method, url, **kwargs):
            kwargs.pop("proxies", None)
            kwargs.pop("stream", None)
            return super().request(method, url, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def close(self):
            try:
                super().close()
            except Exception:
                pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    # 构建 requests 兼容模块
    import types as _types
    _fake_requests = _types.ModuleType("requests")
    _fake_requests.__dict__.update({
        k: v for k, v in _real_requests.__dict__.items()
    })
    _fake_requests.Session = _ChromeSession

    def _no_proxy_get(url, **kwargs):
        kwargs.pop("proxies", None)
        kwargs.pop("stream", None)
        return _cffi_get(url, impersonate="chrome110", **kwargs)

    def _no_proxy_post(url, **kwargs):
        kwargs.pop("proxies", None)
        kwargs.pop("stream", None)
        return _cffi_post(url, impersonate="chrome110", **kwargs)

    _fake_requests.get = _no_proxy_get
    _fake_requests.post = _no_proxy_post

    sys.modules["requests"] = _fake_requests

    # 清代理环境变量
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
               "ALL_PROXY", "all_proxy"):
        os.environ.pop(_k, None)
    os.environ["NO_PROXY"] = "*"

except ImportError:
    pass

# ── 修复 akshare 中依赖带数字前缀 CDN 节点的函数 ─────────────────────────────
# 部分东方财富 CDN 节点（80.push2 / 82.push2）有更严格的 WAF，
# 使用 BoringSSL（curl_cffi）连接时会被断开。
# index_code_id_map_em 用于获取指数代码->市场 ID 映射，数据是静态的，
# 直接返回硬编码映射即可跳过该网络请求。
try:
    import akshare as _ak
    import functools as _functools

    # 主要 A 股指数市场代码：上海(1) / 深圳(0)
    _INDEX_MARKET_MAP: dict = {
        "000001": "1", "000016": "1", "000300": "1", "000500": "1",
        "000688": "1", "000852": "1", "000905": "1", "000906": "1",
        "000010": "1", "000015": "1", "000050": "1", "000068": "1",
        "399001": "0", "399002": "0", "399003": "0", "399004": "0",
        "399005": "0", "399006": "0", "399300": "0", "399400": "0",
        "399401": "0", "399550": "0", "399673": "0",
    }

    @_functools.lru_cache()
    def _static_index_code_id_map_em() -> dict:
        return _INDEX_MARKET_MAP

    # 替换 akshare 内部的 index_code_id_map_em
    import akshare.index.stock_zh_index_daily_em as _em_mod
    if hasattr(_em_mod, "index_code_id_map_em"):
        _em_mod.index_code_id_map_em = _static_index_code_id_map_em
    # 同时替换顶层导出
    if hasattr(_ak, "index_code_id_map_em"):
        _ak.index_code_id_map_em = _static_index_code_id_map_em

except Exception:
    pass  # 安全降级，不影响启动
# ─────────────────────────────────────────────────────────────────────────────


import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 将项目根目录加入路径，使 core 包可被导入
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.routers import market, backtest, factor


async def _warm_cache() -> None:
    """服务启动后在后台异步预热常用数据，用户首次访问直接命中缓存。"""
    import logging
    from datetime import datetime, timedelta
    from core.data.market import get_market_data

    loop = asyncio.get_event_loop()
    md = get_market_data()
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

    tasks = [
        ("指数快照", lambda: md.get_index_snapshot()),
        ("涨跌幅榜", lambda: md.get_market_movers(10)),
        ("沪深300历史", lambda: md.get_index_history("sh000300", start, end)),
        ("创业板指历史", lambda: md.get_index_history("sz399006", start, end)),
    ]
    for name, fn in tasks:
        try:
            await loop.run_in_executor(None, fn)
            logger.info(f"缓存预热完成: {name}")
        except Exception as e:
            logger.warning(f"缓存预热失败 [{name}]: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时异步预热，不阻塞服务启动
    asyncio.create_task(_warm_cache())
    yield


app = FastAPI(
    title="fi_earn API",
    description="A股量化交易研究平台 REST API",
    version="1.0.0",
    lifespan=lifespan,
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
