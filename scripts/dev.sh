#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
API_PORT=${API_PORT:-9000}
WEB_PORT=${WEB_PORT:-5173}

log() {
  printf '\033[1;34m[dev]\033[0m %s\n' "$1"
}

free_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti tcp:"$port" || true)
    if [ -n "$pids" ]; then
      log "端口 $port 被占用，尝试结束进程 $pids"
      echo "$pids" | xargs -r kill >/dev/null 2>&1 || true
      sleep 1
      local remaining
      remaining=$(lsof -ti tcp:"$port" || true)
      if [ -n "$remaining" ]; then
        log "进程 $remaining 未响应，尝试强制结束"
        echo "$remaining" | xargs -r kill -9 >/dev/null 2>&1 || true
        sleep 1
      fi
    fi
  fi
}

# Backend setup
if [ ! -d "$VENV_DIR" ]; then
  log "创建 Python 虚拟环境 .venv"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
if ! command -v pip >/dev/null 2>&1; then
  log "虚拟环境缺少 pip，尝试安装 ensurepip"
  "$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || {
    log "ensurepip 执行失败，请检查 Python 安装"
    exit 1
  }
fi
log "安装后端依赖"
"$VENV_DIR/bin/python" -m pip install -q -r "$BACKEND_DIR/requirements.txt"

log "启动 FastAPI (端口 $API_PORT)"
free_port "$API_PORT"
PYTHONPATH="$ROOT_DIR" "$VENV_DIR/bin/python" -m uvicorn backend.app:app \
  --host 0.0.0.0 --port "$API_PORT" --reload &
BACKEND_PID=$!
deactivate >/dev/null 2>&1 || true

cleanup() {
  log "停止服务"
  if ps -p "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT

# Frontend setup
log "安装前端依赖"
(cd "$FRONTEND_DIR" && npm install)

log "启动 Vite (端口 $WEB_PORT)"
free_port "$WEB_PORT"
(cd "$FRONTEND_DIR" && VITE_API_BASE="http://localhost:$API_PORT" npm run dev -- --host --port "$WEB_PORT")
