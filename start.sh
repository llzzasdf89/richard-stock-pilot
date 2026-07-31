#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
DAILY_SYNC_BAR_COUNT=60
DAILY_SYNC_MARKETS="US HK"
DAILY_SYNC_MIN_MARKET_CAP=50000000000
DAILY_SYNC_MIN_AVG_VOLUME=1000000
DAILY_SYNC_SOURCE=screener
DAILY_SYNC_FORCE=0
BACKEND_PID=""
FRONTEND_PID=""

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

cleanup() {
  if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
}

ensure_env_file() {
  if [ ! -f "${ROOT_DIR}/.env" ]; then
    log "未发现 .env，已从 .env.example 创建占位文件"
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  fi
}

load_env_file() {
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
  DAILY_SYNC_BAR_COUNT="${DAILY_SYNC_BAR_COUNT:-60}"
  DAILY_SYNC_SOURCE="${DAILY_SYNC_SOURCE:-screener}"
  DAILY_SYNC_MARKETS="${DAILY_SYNC_MARKETS:-US HK}"
  DAILY_SYNC_MIN_MARKET_CAP="${DAILY_SYNC_MIN_MARKET_CAP:-50000000000}"
  DAILY_SYNC_MIN_AVG_VOLUME="${DAILY_SYNC_MIN_AVG_VOLUME:-1000000}"
  DAILY_SYNC_FORCE="${DAILY_SYNC_FORCE:-0}"
}

install_backend_dependencies() {
  if [ ! -d "${BACKEND_DIR}/.venv" ]; then
    log "未发现后端虚拟环境，正在安装后端依赖"
    (
      cd "${BACKEND_DIR}"
      UV_CACHE_DIR=.uv-cache uv sync
    )
  else
    log "后端依赖已安装"
  fi
}

install_frontend_dependencies() {
  if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
    log "未发现前端 node_modules，正在安装前端依赖"
    (
      cd "${FRONTEND_DIR}"
      npm install
    )
  else
    log "前端依赖已安装"
  fi
}

ensure_daily_screening_data() {
  log "检查当天日线筛选数据"
  if [ "${DAILY_SYNC_FORCE}" != "1" ] && (
    cd "${BACKEND_DIR}"
    UV_CACHE_DIR=.uv-cache uv run python -m app.scripts.has_daily_screening_data
  ); then
    log "当天日线筛选数据已存在，跳过批处理同步"
    return
  fi

  log "当天日线筛选数据不存在，开始执行批处理同步"
  if [ "${DAILY_SYNC_SOURCE}" = "symbols" ]; then
    if [ -z "${DAILY_SYNC_SYMBOLS:-}" ]; then
      printf 'DAILY_SYNC_SOURCE=symbols，但 DAILY_SYNC_SYMBOLS 未配置，无法执行同步。\n' >&2
      exit 1
    fi
    # shellcheck disable=SC2086
    if ! (
      cd "${BACKEND_DIR}"
      UV_CACHE_DIR=.uv-cache uv run python -m app.scripts.sync_daily_screening --bar-count "${DAILY_SYNC_BAR_COUNT}" --symbols ${DAILY_SYNC_SYMBOLS}
    ); then
      printf '日线批处理同步失败，停止启动程序。\n' >&2
      exit 1
    fi
    return
  fi

  # shellcheck disable=SC2086
  if ! (
    cd "${BACKEND_DIR}"
    UV_CACHE_DIR=.uv-cache uv run python -m app.scripts.sync_daily_screening \
      --bar-count "${DAILY_SYNC_BAR_COUNT}" \
      --markets ${DAILY_SYNC_MARKETS} \
      --min-market-cap "${DAILY_SYNC_MIN_MARKET_CAP}" \
      --min-avg-volume "${DAILY_SYNC_MIN_AVG_VOLUME}"
  ); then
    printf '日线批处理同步失败，停止启动程序。\n' >&2
    exit 1
  fi
}

start_backend() {
  log "启动后端：http://127.0.0.1:${BACKEND_PORT}"
  (
    cd "${BACKEND_DIR}"
    UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT}"
  ) &
  BACKEND_PID="$!"
}

start_frontend() {
  log "启动前端：http://127.0.0.1:${FRONTEND_PORT}"
  (
    cd "${FRONTEND_DIR}"
    VITE_BACKEND_PORT="${BACKEND_PORT}" npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}"
  ) &
  FRONTEND_PID="$!"
}

trap cleanup EXIT INT TERM

require_command uv
require_command npm
ensure_env_file
load_env_file
install_backend_dependencies
install_frontend_dependencies
ensure_daily_screening_data
start_backend
start_frontend

log "前后端已启动，按 Ctrl+C 停止"

while kill -0 "${BACKEND_PID}" >/dev/null 2>&1 && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; do
  sleep 1
done

cleanup
