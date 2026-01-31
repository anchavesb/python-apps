#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -U pip wheel
# Install all apps in editable mode
for app in apps/*; do
  if [ -f "$app/pyproject.toml" ]; then
    echo "Installing $app"
    pip install -e "$app"
  fi
done
pip install -U pytest

echo "Dev environment ready. Activate with: source .venv/bin/activate"
