#!/usr/bin/env bash
# Setup script for Dolores services
# Run when network access to PyPI is available (e.g., off corporate VPN)
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"
PIP="${VENV}/bin/pip"

echo "=== Dolores Setup ==="
echo "Repo root: ${REPO_ROOT}"

# Create venv if needed
if [ ! -f "${VENV}/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "${VENV}"
fi

echo "Upgrading pip..."
"${PIP}" install -U pip wheel

echo ""
echo "Installing dolores-common..."
"${PIP}" install -e "${REPO_ROOT}/libs/dolores-common"

echo ""
echo "Installing dolores services (lightweight)..."
for app in dolores-stt dolores-brain dolores-assistant dolores-cli; do
    echo "  Installing ${app}..."
    "${PIP}" install -e "${REPO_ROOT}/apps/${app}"
done

echo ""
echo "Installing dolores-tts (this may take a while - downloads torch + XTTS)..."
"${PIP}" install -e "${REPO_ROOT}/apps/dolores-tts"

echo ""
echo "Installing test dependencies..."
"${PIP}" install -U pytest

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start services (each in a separate terminal):"
echo "  source ${VENV}/bin/activate"
echo ""
echo "  # 1. Start Ollama (if using local LLM)"
echo "  ollama serve"
echo "  ollama pull llama3.2"
echo ""
echo "  # 2. Start backend services"
echo "  dolores-brain       # port 8003 - LLM routing"
echo "  dolores-stt         # port 8001 - speech-to-text"
echo "  dolores-tts         # port 8002 - text-to-speech"
echo "  dolores-assistant   # port 8000 - orchestrator"
echo ""
echo "  # 3. Chat!"
echo "  dolores-cli chat"
echo ""
echo "Or test health: ./scripts/test-dolores-services.sh"
