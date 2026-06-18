.PHONY: start stop backend frontend install clean logs help

# 端口配置
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
LOG_DIR = logs

help:
	@echo ""
	@echo "fi_earn · A股量化研究平台"
	@echo ""
	@echo "  make start      一键启动（后端 + 前端）"
	@echo "  make stop       停止所有服务"
	@echo "  make backend    仅启动 FastAPI 后端 (：$(BACKEND_PORT))"
	@echo "  make frontend   仅启动 Next.js 前端 (:$(FRONTEND_PORT))"
	@echo "  make install    安装所有依赖"
	@echo "  make logs       查看服务日志"
	@echo "  make clean      清理缓存和日志"
	@echo ""

# 一键启动
start:
	@bash start.sh

# 分别启动
backend:
	@mkdir -p $(LOG_DIR)
	@echo "[INFO] 启动 FastAPI 后端..."
	@PYTHON=$$(for p in python3.11 python3.12 python3.13 python3; do \
	    which $$p 2>/dev/null && break; \
	  done); \
	  $$PYTHON -m uvicorn backend.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload

frontend:
	@echo "[INFO] 启动 Next.js 前端..."
	@cd frontend && npm run dev -- --port $(FRONTEND_PORT)

# 停止服务
stop:
	@echo "[INFO] 停止服务..."
	@[ -f $(LOG_DIR)/backend.pid ]  && kill $$(cat $(LOG_DIR)/backend.pid)  2>/dev/null || true
	@[ -f $(LOG_DIR)/frontend.pid ] && kill $$(cat $(LOG_DIR)/frontend.pid) 2>/dev/null || true
	@lsof -ti :$(BACKEND_PORT)  | xargs kill -9 2>/dev/null || true
	@lsof -ti :$(FRONTEND_PORT) | xargs kill -9 2>/dev/null || true
	@echo "[OK] 服务已停止"

# 安装依赖
install:
	@echo "[INFO] 安装 Python 依赖..."
	pip install -r requirements.txt
	@echo "[INFO] 安装 Node.js 依赖..."
	cd frontend && npm install
	@echo "[OK] 依赖安装完成"

# 查看日志
logs:
	@tail -f $(LOG_DIR)/backend.log $(LOG_DIR)/frontend.log 2>/dev/null || echo "日志文件不存在，请先启动服务"

# 清理
clean:
	@echo "[INFO] 清理缓存..."
	@rm -rf cache/ logs/ frontend/.next/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "[OK] 清理完成"
