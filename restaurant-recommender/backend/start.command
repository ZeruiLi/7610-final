#!/usr/bin/env bash
# macOS double-click starter for Restaurant Recommender
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
chmod +x scripts/dev.sh || true
exec bash scripts/dev.sh

