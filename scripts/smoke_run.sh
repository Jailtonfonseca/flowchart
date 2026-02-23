#!/usr/bin/env bash
set -euo pipefail

export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-dummy_key}"

# Build and run
docker compose up --build -d

# Wait for streamlit and verify HTTP code 200/302
ok=0
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 || true)
  if [[ "$code" == "200" || "$code" == "302" ]]; then
    ok=1
    break
  fi
  sleep 2
done

if [[ "$ok" != "1" ]]; then
  echo "Smoke test failed: streamlit did not respond with 200/302"
  exit 1
fi

echo "Smoke test passed"
