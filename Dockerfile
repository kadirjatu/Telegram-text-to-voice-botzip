# Telegram bot + Mini App backend, bundled as ONE deployable service
# (Railway's free plan only allows a single service per project).
#
# This lives inside a pnpm workspace monorepo, so the Docker BUILD CONTEXT
# must be the repository root:
#   Dockerfile Path:      Dockerfile
#   Docker Build Context: . (repo root)
#
# The Mini App listens on the PORT env var Railway injects automatically.
# The Telegram bot doesn't need a port (long-polling), so only one port is
# used for the whole container.

FROM node:24-slim

RUN corepack enable && \
    corepack prepare pnpm@10.26.1 --activate && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-venv ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# uv manages the Python deps (see pyproject.toml at the repo root)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy the whole workspace (needed so pnpm/uv can resolve workspace deps).
COPY . .

# Python deps for the Telegram bot
RUN uv sync --frozen

# Node deps + build for the Mini App backend
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @workspace/api-server run build

ENV NODE_ENV=production

# Run both processes in one container: the bot (polling, no port) and the
# Mini App backend (listens on $PORT). If either exits, the container exits
# too, so Railway's restart policy takes over -- keeps this simple, matching
# the same approach as the local start-all.sh dev script.
CMD ["bash", "-c", "\
  (cd telegram-bot && /app/.venv/bin/python bot.py) & BOT_PID=$!; \
  (PORT=${PORT:-8080} node --enable-source-maps telegram-bot/mini-app/dist/index.mjs) & APP_PID=$!; \
  wait -n $BOT_PID $APP_PID; \
  EXIT_CODE=$?; \
  kill $BOT_PID $APP_PID 2>/dev/null; \
  exit $EXIT_CODE \
"]
