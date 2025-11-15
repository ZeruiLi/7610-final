#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.logs"
PID_DIR="$ROOT_DIR/.pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

kill_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti:"$port" || true)
    if [[ -n "$pids" ]]; then
      echo "[start-dev] Killing processes on port $port ($pids)"
      kill $pids || true
    fi
  fi
}

start_backend() {
  echo "[start-dev] Starting backend (FastAPI on 8010)"
  kill_port 8010

  local venv_dir="$BACKEND_DIR/.venv"
  if [[ ! -d "$venv_dir" ]]; then
    echo "[start-dev] Creating python venv at $venv_dir"
    if command -v python3.11 >/dev/null 2>&1; then
      python3.11 -m venv "$venv_dir"
    else
      python3 -m venv "$venv_dir"
    fi
  fi

  source "$venv_dir/bin/activate"
  # keep deps fresh (cached installs are fast)
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r "$BACKEND_DIR/requirements.txt" >/dev/null
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    set -a
    source "$BACKEND_DIR/.env"
    set +a
  fi

  pushd "$BACKEND_DIR/src" >/dev/null
  PYTHONPATH=. nohup python -m uvicorn main:app --port 8010 --log-level warning \
    >"$LOG_DIR/backend.log" 2>&1 &
  local pid=$!
  popd >/dev/null
  deactivate

  echo "$pid" > "$PID_DIR/backend.pid"
  echo "[start-dev] Backend PID $pid (logs: $LOG_DIR/backend.log)"

  # health check
  echo -n "[start-dev] Waiting for backend healthz"
  for i in {1..30}; do
    if curl -sf "http://localhost:8010/healthz" >/dev/null 2>&1; then
      echo " - OK"
      break
    fi
    echo -n "."
    sleep 1
  done
}

start_frontend() {
  echo "[start-dev] Starting frontend (Vite on 5173)"
  kill_port 5173

  pushd "$FRONTEND_DIR" >/dev/null
  local node_prefix=""
  if [[ -x /opt/homebrew/opt/node@20/bin/node ]]; then
    node_prefix="/opt/homebrew/opt/node@20/bin"
  elif [[ -x /opt/homebrew/bin/node ]]; then
    node_prefix="/opt/homebrew/bin"
  fi

  if [[ -n "$node_prefix" ]]; then
    export PATH="$node_prefix:$PATH"
  fi

  if [[ ! -d node_modules ]]; then
    echo "[start-dev] Installing frontend dependencies"
    npm install >/dev/null
  fi

  nohup npm run dev -- --host 0.0.0.0 --port 5173 \
    >"$LOG_DIR/frontend.log" 2>&1 &
  local pid=$!
  popd >/dev/null

  echo "$pid" > "$PID_DIR/frontend.pid"
  echo "[start-dev] Frontend PID $pid (logs: $LOG_DIR/frontend.log)"
}

start_backend
start_frontend

echo "[start-dev] Services ready:"
echo "  - Backend: http://localhost:8010/"
echo "  - Frontend: http://localhost:5173/"
echo "[start-dev] To stop:"
echo "  kill \
    \$(cat '$PID_DIR/backend.pid') \
    \$(cat '$PID_DIR/frontend.pid')"
