#!/usr/bin/env bash
# Manually start both services (Telegram bot, Mini App) together
# from the terminal, without touching Replit's "Run" button/workflows.
#
# Usage:
#   ./start-all.sh          # start both, logs interleaved in this shell
#   Ctrl+C                  # stops both together
#
# Logs for each service also go to ./logs/*.log so you can tail them separately.

set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs
pids=()

cleanup() {
  echo ""
  echo "Stopping all services..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "All services stopped."
}
trap cleanup EXIT INT TERM

echo "Starting Telegram bot..."
(cd telegram-bot && python bot.py) >logs/telegram-bot.log 2>&1 &
pids+=($!)

echo "Starting Mini App API server (port 8080)..."
(cd artifacts/api-server && PORT=8080 NODE_ENV=production pnpm run build && PORT=8080 NODE_ENV=production node --enable-source-maps ./dist/index.mjs) >logs/api-server.log 2>&1 &
pids+=($!)

echo ""
echo "Both services started (PIDs: ${pids[*]})."
echo "Tail logs with: tail -f logs/telegram-bot.log logs/api-server.log"
echo "Press Ctrl+C to stop all."

wait
