# Text-to-Voice Telegram Bot

A Telegram bot that converts text into natural-sounding voice messages using Microsoft Edge-TTS (free, no API key/Azure account needed).

## Run & Operate

- The bot runs via the `Telegram TTS Bot` workflow: `cd telegram-bot && python bot.py` (polling mode, no port needed)
- The Mini App's backend now lives at `telegram-bot/mini-app/` (moved out of `artifacts/` on 2026-07-13, see Architecture decisions) and runs via the plain `Mini App` workflow: `PORT=8080 pnpm --filter @workspace/api-server run dev`, serving `/api/*`. A `[[ports]]` mapping (`localPort = 8080` → `externalPort = 80`) in `.replit` exposes it publicly since it's no longer a managed artifact.
- Required secrets: `TELEGRAM_BOT_TOKEN` (Telegram bot token from BotFather).
- Mini App button URL needs a public HTTPS domain, resolved in this order: `MINI_APP_PUBLIC_DOMAIN` (manual override) → `RAILWAY_PUBLIC_DOMAIN` (auto-set once Railway's "Public Networking" is enabled for the service) → `REPLIT_DEV_DOMAIN`. If none are set, the Mini App button/menu is skipped instead of pointing at a broken URL.
- After a fresh git import/clone, run `pnpm install` at the repo root once before starting the `Mini App` workflow — its `node_modules` aren't committed.
- The standalone OpenAI-compatible TTS REST API (`tts-api/`, Dockerfile, `TTS_API_KEY` secret) was removed on 2026-07-13 to keep the Railway free-plan deployment down to a single service. Only the Telegram bot and the Mini App backend remain.

## Stack

- Python 3.11, `python-telegram-bot` (async, polling)
- `edge-tts` for speech synthesis (24 languages, male/female neural voices)
- `ffmpeg` to convert MP3 → OGG/Opus for Telegram voice messages
- `langdetect` for automatic language detection
- Managed with `uv`/`pyproject.toml` at the repo root (not part of the pnpm workspace)

## Where things live

- `telegram-bot/bot.py` — entrypoint, registers `/start`, `/help`, and the TTS feature
- `telegram-bot/tts/config.py` — limits, defaults, directories
- `telegram-bot/tts/voices.py` — language → voice map, auto-detect, `get_available_voices()`
- `telegram-bot/tts/generator.py` — Edge-TTS → MP3 → ffmpeg → OGG/Opus, caching, cancellation
- `telegram-bot/tts/handlers.py` — `/tts`, `/voice`, `/settings`, `/myvoice`, `/autodetect`, `/cancel`
- `telegram-bot/tts/utils.py` — filename safety, chunking, temp-file retention, JSON prefs store, logging
- `telegram-bot/data/` — runtime-only: cache, temp scratch files, logs, user prefs (gitignored)

## Architecture decisions

- Built as a standalone Python service outside the pnpm/artifact system (no matching artifact type exists for a polling Telegram bot); registered as a plain workflow instead.
- User voice/language/rate/pitch/volume preferences persist in a small JSON file (`telegram-bot/data/user_prefs.json`), not the project database — no DB was needed for this feature.
- Generated voice notes are cached by a hash of (text, voice, rate, pitch, volume) so repeat requests are instant; temp scratch files are capped at 2 and pruned automatically.
- Punjabi was requested but Microsoft Edge TTS has no Punjabi neural voice today — the bot says so explicitly in the `/voice` menu instead of silently substituting another language.
- 2026-07-13: Mini App backend moved from the managed `artifacts/api-server` artifact to `telegram-bot/mini-app/` and deregistered as an artifact, so the Telegram bot and Mini App can eventually ship as one bundled Railway service instead of two. It's now a plain workflow; path-resolution code in `pythonBridge.ts` needed no changes since the new location is the same depth from the repo root. Public HTTPS access on Replit required manually adding a `[[ports]]` mapping in `.replit` (localPort 8080 → externalPort 80) since a plain workflow's port isn't proxied automatically the way an artifact's is.

## Product

- `/tts` → prompts for text, or accepts it directly (`/tts <text>`), or converts a replied-to message. Every request then asks (inline buttons) which language and male/female voice to use before generating — nothing is silently defaulted.
- `/voice` → sets a saved default language/voice for reference via `/myvoice`; `/autodetect` re-enables automatic language detection as a one-tap option in the per-request picker.
- `/settings` → adjust speech rate, pitch, and volume; `/myvoice` shows current saved settings; `/cancel` stops an in-progress generation.
- `/app` → opens the Telegram Mini App (same feature, simple purple/pink web UI): type text, tap a language chip, tap Male/Female, get an audio player + download link. Single text request only (up to 5000 characters), no chunking, by design (kept simple).
- The Mini App also opens from the persistent Menu Button (the icon beside the message input's emoji/attachment icon), set once at bot startup via `set_chat_menu_button` — not just the inline "Open Mini App" button in chat.
- Every conversion (bot and mini app) first **translates** the text into the language the user picked (via `tts/translator.py`, Google Translate free endpoint through `deep-translator`), then speaks the translated text — so the output is always actually in the chosen language, not the original words read with that language's accent. Falls back to the original text if translation fails.
- Long text via the bot (>5000 characters) is automatically split into sequential voice messages; the mini app caps at 5000 characters per request.
- Works in private chats, groups, and supergroups.

## Mini App architecture

- Frontend: plain HTML/CSS/JS (no build step) at `telegram-bot/mini-app/public/webapp/`, served by the API server at `/api/app/`.
- Backend: routes in `telegram-bot/mini-app/src/routes/miniApp.ts` (`GET /api/mini-app/languages`, `POST /api/mini-app/generate`).
- The Node routes never reimplement TTS — they shell out to `python -m tts.cli` (`telegram-bot/tts/cli.py`) via `telegram-bot/mini-app/src/lib/pythonBridge.ts`, so the bot and the mini app always share one voice pipeline, cache, and language table.
- Both the bot and the mini app's backend start together under the existing "Project" run button (parallel workflows) — no separate command needed.
- `telegram-bot/mini-app` is a pnpm workspace package (`pnpm-workspace.yaml` lists it explicitly since it's outside `artifacts/*`), still named `@workspace/api-server` and still depending on `@workspace/api-zod`/`@workspace/db` via `workspace:*`.

## User preferences

- User wants a brand-new Telegram bot (not an integration into a pre-existing one — none existed in this project).

## Gotchas

- This bot's Telegram account currently has group privacy mode ON (default for new bots), so in groups it only receives commands and replies to its own messages — the bare `/tts` → "send me the text" plain-text follow-up only works reliably in private chats or when the group disables privacy mode via BotFather (`/setprivacy`).
- Always restart the `Telegram TTS Bot` workflow after editing anything under `telegram-bot/`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details (applies to `artifacts/` and `lib/`, not the Telegram bot).
