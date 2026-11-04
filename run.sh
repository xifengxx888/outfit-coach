#!/usr/bin/env bash
# 一键启动：后端(FastAPI :8000) + 前端(Vite :5173)
# 用法：./run.sh   （Ctrl+C 停止，自动清理两个进程）
set -euo pipefail

cd "$(dirname "$0")"

# 环境自检：缺什么提示什么
if [ ! -d .venv ]; then
  echo "错误：缺少 .venv，请先初始化环境（docs/07-开工前检查.md 第 0 节）" >&2
  exit 1
fi
if [ ! -d src/web/node_modules ]; then
  echo "提示：src/web/node_modules 不存在，正在 npm install ..."
  (cd src/web && npm install)
fi

cleanup() {
  echo ""
  echo "停止服务 ..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "启动后端 http://127.0.0.1:8000"
.venv/bin/uvicorn src.api.app:app --reload --port 8000 &
BACKEND_PID=$!

echo "启动前端 http://127.0.0.1:5173"
(cd src/web && npm run dev) &
FRONTEND_PID=$!

wait
