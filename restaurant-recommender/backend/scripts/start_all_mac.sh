#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[start] Restaurant Recommender – macOS one‑shot starter"

# 1) Load env (Geoapify key etc.)
if [[ -f .env ]]; then
  echo "[start] Loading .env"
  set -a; source .env; set +a
fi
if [[ -z "${GEOAPIFY_API_KEY:-}" ]]; then
  echo "[start][error] GEOAPIFY_API_KEY not set. Edit $ROOT_DIR/.env (see .env.example)." >&2
  exit 1
fi

# 2) Ensure Homebrew (best‑effort)
if ! command -v brew >/dev/null 2>&1; then
  echo "[start] Homebrew not found. Installing (this may prompt password/confirmation)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true
  eval "$($(brew --prefix)/bin/brew shellenv)" || true
fi

# 3) Ensure Ollama (best‑effort) – improves parsing stability
if ! command -v ollama >/dev/null 2>&1; then
  echo "[start] Installing ollama via Homebrew..."
  brew install ollama || true
fi

if command -v ollama >/dev/null 2>&1; then
  if ! curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[start] Starting ollama daemon..."
    nohup ollama serve >/dev/null 2>&1 &
    for i in {1..20}; do
      if curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then break; fi
      sleep 1
    done
  fi
  if ! ollama list | grep -q "^llama3.2\b"; then
    echo "[start] Pulling model llama3.2 (~1–2GB, first time only)..."
    ollama pull llama3.2 || true
  fi
else
  echo "[start] Ollama unavailable; fallback rules will be used."
fi

# 4) Ensure Python3 & venv
if ! command -v python3 >/dev/null 2>&1; then
  echo "[start] Installing Python 3 via Homebrew..."
  brew install python@3.11 || true
fi

echo "[start] Creating/updating venv..."
PY=python3
$PY -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
if ! python -m pip install -e . >/dev/null 2>&1; then
  echo "[start] Editable install failed; falling back to requirements.txt"
  python -m pip install -r requirements.txt >/dev/null
fi

# 5) (Optional) Build Flutter Web and host under /app
if command -v flutter >/dev/null 2>&1; then
  echo "[start] Building Flutter Web front-end..."
  bash scripts/build_flutter_web.sh || echo "[start] Flutter build failed; continuing with classic static page."
fi

# 6) Launch backend & open browser
echo "[start] Launching backend at http://localhost:8010/"
# Decide which URL to open based on build presence
APP_INDEX="$ROOT_DIR/src/static/app/index.html"
if [[ -f "$APP_INDEX" ]]; then
  OPEN_URL="http://localhost:8010/app"
else
  OPEN_URL="http://localhost:8010/"
fi
(sleep 3; open "$OPEN_URL") &
cd src
exec python -m uvicorn main:app --reload --port 8010
