"""
Configuration and constants for the Text-To-Voice (Edge-TTS) feature.

No API key and no Azure account are required -- edge-tts talks to the free
public Microsoft Edge "Read Aloud" service.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Bot token (same token your existing bot already uses)
# ---------------------------------------------------------------------------
_raw_token = os.environ.get("TELEGRAM_BOT_TOKEN")
BOT_TOKEN: str | None = _raw_token.strip() if _raw_token else _raw_token

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = DATA_DIR / "temp"       # scratch working files (mp3 -> ogg conversion)
CACHE_DIR = DATA_DIR / "cache"     # reusable generated voice notes
LOG_DIR = DATA_DIR / "logs"
PREFS_FILE = DATA_DIR / "user_prefs.json"

for _d in (DATA_DIR, TEMP_DIR, CACHE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Text limits
# ---------------------------------------------------------------------------
# A single Edge-TTS request is comfortable up to this many characters.
CHUNK_CHAR_LIMIT = 5000
# Hard ceiling on the total request size (protects the bot from abuse/flood).
# Anything above this is rejected outright instead of silently truncated.
MAX_TOTAL_CHAR_LIMIT = 20000

# ---------------------------------------------------------------------------
# Temp file retention
# ---------------------------------------------------------------------------
# Only this many scratch files are ever kept in TEMP_DIR at once; the oldest
# ones are deleted automatically as soon as this limit is exceeded.
MAX_TEMP_FILES = 2

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHE_ENABLED = True
MAX_CACHE_FILES = 200  # soft cap, oldest entries pruned beyond this

# ---------------------------------------------------------------------------
# Default voice settings (Edge-TTS accepts these exact string formats)
# ---------------------------------------------------------------------------
DEFAULT_RATE = "+0%"
DEFAULT_PITCH = "+0Hz"
DEFAULT_VOLUME = "+0%"

# Kept subtle on purpose: pushing rate/pitch further than this makes the
# neural voices sound noticeably artificial/robotic.
RATE_OPTIONS = ["-5%", "-2%", "+0%", "+2%", "+5%"]
PITCH_OPTIONS = ["-2Hz", "-1Hz", "+0Hz", "+1Hz", "+2Hz"]
VOLUME_OPTIONS = ["-50%", "-25%", "+0%", "+25%", "+50%"]

DEFAULT_LANGUAGE = "English"
DEFAULT_GENDER = "female"

# ---------------------------------------------------------------------------
# Mini App (Telegram Web App) -- served by the Node API server, which shells
# out to `python -m tts.cli` to reuse this same pipeline. See
# telegram-bot/mini-app/src/routes/miniApp.ts.
#
# The public domain differs per host:
#   - Replit dev:        REPLIT_DEV_DOMAIN
#   - Railway:            RAILWAY_PUBLIC_DOMAIN (set automatically once the
#                          service has "Public Networking" enabled)
#   - Manual override:    MINI_APP_PUBLIC_DOMAIN (any host not covered above)
# Without one of these, there is no public HTTPS URL to hand Telegram, so the
# Mini App button is left unset (see bot.py) instead of pointing at a broken
# URL.
# ---------------------------------------------------------------------------
_public_domain = (
    os.environ.get("MINI_APP_PUBLIC_DOMAIN")
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    or os.environ.get("REPLIT_DEV_DOMAIN")
)
MINI_APP_URL: str | None = f"https://{_public_domain}/api/app/" if _public_domain else None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = LOG_DIR / "tts.log"
