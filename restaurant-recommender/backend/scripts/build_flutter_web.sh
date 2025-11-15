#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)" # backend root
APP_DIR="$ROOT_DIR/../../../../flutter_app"
STATIC_DIR="$ROOT_DIR/src/static/app"

echo "[flutter] Building Flutter Web app..."

if ! command -v flutter >/dev/null 2>&1; then
  echo "[flutter] Flutter not found. Attempting install via Homebrew (may require confirmation)..."
  if command -v brew >/dev/null 2>&1; then
    brew install --cask flutter || true
  else
    echo "[flutter] Homebrew not available. Please install Flutter manually: https://docs.flutter.dev/get-started/install"
    exit 1
  fi
fi

flutter --version || true
flutter config --enable-web || true

cd "$APP_DIR"
flutter pub get
# Build Flutter web (Flutter >=3.35 no longer needs/accepts --web-renderer)
flutter build web --release --dart-define=API_BASE_URL=http://localhost:8010

mkdir -p "$STATIC_DIR"
cp -r "build/web"/* "$STATIC_DIR"/
echo "[flutter] Web app copied to $STATIC_DIR"
