#!/usr/bin/env bash
# Test each Dolores service health endpoint
# Usage: ./scripts/test-dolores-services.sh
set -e

echo "=== Testing Dolores Services ==="

check() {
    local name=$1
    local port=$2
    printf "  %-20s " "${name} (:${port})"
    if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
        echo "✓ healthy"
        curl -s "http://localhost:${port}/health" | python3 -m json.tool 2>/dev/null
    else
        echo "✗ unreachable"
    fi
}

check "dolores-assistant" 8000
check "dolores-stt" 8001
check "dolores-tts" 8002
check "dolores-brain" 8003

echo ""
echo "=== Quick Smoke Tests ==="

# Test brain chat (if brain is up and Ollama is running)
if curl -sf "http://localhost:8003/health" > /dev/null 2>&1; then
    echo "Testing brain /v1/chat..."
    curl -s -X POST http://localhost:8003/v1/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "Say hello in one sentence."}' | python3 -m json.tool
else
    echo "Brain not running, skipping chat test"
fi

# Test STT transcribe (if STT is up, needs a WAV file)
if curl -sf "http://localhost:8001/health" > /dev/null 2>&1; then
    echo "STT is up. Test with: curl -X POST http://localhost:8001/v1/transcribe -F 'file=@test.wav'"
else
    echo "STT not running, skipping"
fi

echo ""
echo "Done."
