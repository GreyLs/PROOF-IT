#!/bin/sh
set -eu
export OLLAMA_HOST=127.0.0.1:11434
ollama serve >/tmp/ollama-bootstrap.log 2>&1 &
model_pid=$!
trap 'kill "$model_pid" 2>/dev/null || true' EXIT
attempt=0
until ollama list >/dev/null 2>&1; do
    attempt=$((attempt+1))
    if [ "$attempt" -gt 60 ]; then exit 1; fi
    sleep 1
done
ollama pull "${OLLAMA_MODEL:-qwen3:8b}"
