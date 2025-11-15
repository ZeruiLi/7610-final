#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."  # backend root

if [[ -f .env ]]; then
  echo "[dev] Loading .env"
  set -a; source .env; set +a
fi

if [[ -z "${GEOAPIFY_API_KEY:-}" ]]; then
  echo "[dev][error] GEOAPIFY_API_KEY is not set. Copy .env.example to .env and fill your key." >&2
  exit 1
fi

echo "[dev] Geoapify key present."

OS_NAME=$(uname -s || true)

# Optional: ensure Ollama running with llama3.2 for better parsing
if command -v ollama >/dev/null 2>&1; then
  echo "[dev] Ollama found. Ensuring daemon is running..."
  # Try to start serve in background if not responding
  if ! curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[dev] Starting ollama serve in background..."
    nohup ollama serve >/dev/null 2>&1 &
    # wait up to 15s for readiness
    for i in {1..15}; do
      if curl -sS http://localhost:11434/api/tags >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi
  echo "[dev] Ensuring model llama3.2 is available..."
  if ! ollama list | grep -q "^llama3.2\b"; then
    echo "[dev] Pulling llama3.2 (one-time download, ~1–2GB)..."
    ollama pull llama3.2 || true
  fi
else
  echo "[dev] Ollama not found. Skipping LLM (fallback rules will be used)."
  echo "      macOS 安装建议: brew install ollama && ollama serve"
fi

echo "[dev] Starting backend at http://localhost:8010"
echo "[dev] Ensuring Python venv and deps..."
if command -v python3 >/dev/null 2>&1; then
  python3 -m venv .venv || true
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip >/dev/null 2>&1 || true
  if ! python -m pip install -e . >/dev/null 2>&1; then
    echo "[dev] Editable install failed; falling back to requirements.txt"
    python -m pip install -r requirements.txt >/dev/null 2>&1 || true
  fi
else
  echo "[dev] 未检测到 python3。请先安装 Python 3（https://www.python.org/downloads/）"
fi

cd src
if [[ "$OS_NAME" == "Darwin" ]]; then
  # Open browser automatically on macOS after slight delay
  (sleep 2; open "http://localhost:8010/") &
fi
exec python -m uvicorn main:app --reload --port 8010
