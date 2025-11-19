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
      kill -9 $pids || true
    fi
  fi
}

start_backend() {
  echo "[start-dev] Starting backend (FastAPI on 8010)"
  kill_port 8010

  local venv_dir="$BACKEND_DIR/.venv"
  if [[ ! -d "$venv_dir" ]]; then
    echo "[start-dev] Creating python venv at $venv_dir"
    python3 -m venv "$venv_dir"
  fi

  source "$venv_dir/bin/activate"
  
  echo "[start-dev] Installing/Updating backend dependencies..."
  python -m pip install --upgrade pip
  python -m pip install -r "$BACKEND_DIR/requirements.txt"

  if [[ -f "$BACKEND_DIR/.env" ]]; then
    set -a
    source "$BACKEND_DIR/.env"
    set +a
  fi

  pushd "$BACKEND_DIR/src" >/dev/null
  PYTHONPATH=. nohup python -m uvicorn main:app --port 8010 --log-level info \
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
      return 0
    fi
    echo -n "."
    sleep 1
  done
  echo " - Failed to start backend. Check logs at $LOG_DIR/backend.log"
  return 1
}

start_frontend() {
  echo "[start-dev] Starting frontend (Vite on 5173)"
  kill_port 5173

  pushd "$FRONTEND_DIR" >/dev/null
  
  if [[ ! -d node_modules ]]; then
    echo "[start-dev] Installing frontend dependencies"
    npm install
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
echo "  kill \$(cat '$PID_DIR/backend.pid') \$(cat '$PID_DIR/frontend.pid')"

