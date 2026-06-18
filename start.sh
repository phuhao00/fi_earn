#!/usr/bin/env bash
# =========================================================
# fi_earn 一键启动脚本
# 同时启动 FastAPI 后端 (8000) 和 Next.js 前端 (3000)
# =========================================================
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="$ROOT/logs"

mkdir -p "$LOG_DIR"

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── 依赖检查 ──────────────────────────────────────────────
check_python() {
  # 优先使用能正常导入项目依赖的 Python
  for candidate in python3.11 python3.12 python3.13 python3; do
    PY_BIN=$(command -v "$candidate" 2>/dev/null || true)
    if [ -n "$PY_BIN" ] && "$PY_BIN" -c "import akshare, fastapi" &>/dev/null 2>&1; then
      PYTHON="$PY_BIN"
      PYTHON_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      info "Python 版本: $PYTHON_VER ($PYTHON)"
      return 0
    fi
  done
  # 回退：找到任意 python3.11
  for extra in ~/.local/bin/python3.11 /opt/homebrew/bin/python3.11; do
    if [ -x "$extra" ]; then
      PYTHON="$extra"
      info "使用备选 Python: $PYTHON"
      return 0
    fi
  done
  error "未找到合适的 Python（需要 3.11+），请先运行: pip install -r requirements.txt"
}

check_node() {
  if ! command -v node &>/dev/null; then
    error "未找到 node，请先安装 Node.js 18+"
  fi
  NODE_VER=$(node --version)
  info "Node 版本: $NODE_VER"
}

install_python_deps() {
  if ! python3 -c "import fastapi" &>/dev/null; then
    info "安装 Python 依赖..."
    pip install -r "$ROOT/requirements.txt" -q
    ok "Python 依赖安装完成"
  else
    ok "Python 依赖已就绪"
  fi
}

install_node_deps() {
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    info "安装 Node.js 依赖..."
    cd "$ROOT/frontend" && npm install -q
    ok "Node.js 依赖安装完成"
  else
    ok "Node.js 依赖已就绪"
  fi
}

# ── 构建 OpenBB 资源（首次运行） ──────────────────────────
build_openbb() {
  if python3 -c "from openbb import obb; obb.equity" &>/dev/null 2>&1; then
    ok "OpenBB 已就绪"
  else
    info "首次运行，构建 OpenBB 资源（约 1 分钟）..."
    python3 -c "import openbb; openbb.build()" 2>/dev/null || warn "OpenBB build 失败，将使用直接 AkShare 模式"
  fi
}

# ── 停止已有进程 ──────────────────────────────────────────
stop_existing() {
  # 检查端口占用
  for PORT in $BACKEND_PORT $FRONTEND_PORT; do
    PID=$(lsof -ti ":$PORT" 2>/dev/null || true)
    if [ -n "$PID" ]; then
      warn "端口 $PORT 已被占用（PID: $PID），正在终止..."
      kill -9 $PID 2>/dev/null || true
      sleep 1
    fi
  done
}

# ── 启动服务 ──────────────────────────────────────────────
start_backend() {
  info "启动 FastAPI 后端（端口 $BACKEND_PORT）..."
  cd "$ROOT"
  nohup "$PYTHON" -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --reload \
    --log-level info \
    > "$LOG_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  echo $BACKEND_PID > "$LOG_DIR/backend.pid"

  # 等待后端就绪
  for i in $(seq 1 20); do
    if curl -s "http://localhost:$BACKEND_PORT/health" &>/dev/null; then
      ok "后端已启动 (PID: $BACKEND_PID) → http://localhost:$BACKEND_PORT"
      ok "API 文档 → http://localhost:$BACKEND_PORT/docs"
      return 0
    fi
    sleep 1
  done
  warn "后端可能未正常启动，请检查日志: $LOG_DIR/backend.log"
}

start_frontend() {
  info "启动 Next.js 前端（端口 $FRONTEND_PORT）..."
  cd "$ROOT/frontend"
  nohup npm run dev -- --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  echo $FRONTEND_PID > "$LOG_DIR/frontend.pid"

  # 等待前端就绪
  for i in $(seq 1 30); do
    if curl -s "http://localhost:$FRONTEND_PORT" &>/dev/null; then
      ok "前端已启动 (PID: $FRONTEND_PID) → http://localhost:$FRONTEND_PORT"
      return 0
    fi
    sleep 2
  done
  warn "前端可能未正常启动，请检查日志: $LOG_DIR/frontend.log"
}

# ── 优雅退出 ──────────────────────────────────────────────
cleanup() {
  echo ""
  info "正在停止服务..."
  [ -f "$LOG_DIR/backend.pid" ]  && kill "$(cat $LOG_DIR/backend.pid)"  2>/dev/null || true
  [ -f "$LOG_DIR/frontend.pid" ] && kill "$(cat $LOG_DIR/frontend.pid)" 2>/dev/null || true
  ok "服务已停止"
  exit 0
}
trap cleanup INT TERM

# ── 主流程 ────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    fi_earn · A股量化研究平台           ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

check_python
check_node
install_python_deps
install_node_deps
build_openbb
stop_existing
start_backend
start_frontend

echo ""
echo -e "${GREEN}✓ 所有服务已启动！${NC}"
echo ""
echo -e "  前端看板  →  ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
echo -e "  API 文档  →  ${BLUE}http://localhost:$BACKEND_PORT/docs${NC}"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo ""

# 跟踪日志输出
tail -f "$LOG_DIR/backend.log" &
wait
