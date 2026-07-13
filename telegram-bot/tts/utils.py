"""
Shared helpers for the Text-To-Voice feature: filename safety, text chunking,
temp-file retention, JSON-file caching of user preferences, and logging setup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from . import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def get_logger() -> logging.Logger:
    logger = logging.getLogger("tts")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    console_handler = logging.StreamHandler()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


log = get_logger()


def log_request(user_id: int, voice: str, chars: int, seconds: float) -> None:
    log.info(
        "user=%s voice=%s chars=%d generation_time=%.2fs",
        user_id, voice, chars, seconds,
    )


def log_error(user_id: int, message: str) -> None:
    log.error("user=%s error=%s", user_id, message)


# ---------------------------------------------------------------------------
# Filename / path safety
# ---------------------------------------------------------------------------

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def safe_filename(name: str) -> str:
    """
    Strip anything that isn't alphanumeric/underscore/dot/dash and collapse
    path separators, preventing path traversal via crafted filenames.
    """
    name = name.replace("/", "_").replace("\\", "_")
    name = _SAFE_CHARS.sub("_", name)
    return name or uuid.uuid4().hex


def new_temp_path(directory: Path, suffix: str) -> Path:
    """A fresh, collision-free path inside `directory` (never derived from user input)."""
    return directory / f"{uuid.uuid4().hex}{suffix}"


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def split_text(text: str, limit: int = config.CHUNK_CHAR_LIMIT) -> list[str]:
    """
    Split `text` into chunks no longer than `limit` characters, preferring to
    break on sentence boundaries, then whitespace, so words are never cut
    mid-way when it can be avoided.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    remaining = text
    sentence_end = re.compile(r"[.!?\u3002\uff01\uff1f]\s+")

    while len(remaining) > limit:
        window = remaining[:limit]

        split_at = -1
        for match in sentence_end.finditer(window):
            split_at = match.end()

        if split_at == -1:
            last_space = window.rfind(" ")
            split_at = last_space if last_space > 0 else limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Temp file retention -- keep only the N most recent scratch files
# ---------------------------------------------------------------------------


def cleanup_temp_files(directory: Path = config.TEMP_DIR, keep: int = config.MAX_TEMP_FILES) -> None:
    """Delete the oldest files in `directory` beyond the most recent `keep`."""
    try:
        files = sorted(
            (p for p in directory.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except FileNotFoundError:
        return

    for old_file in files[keep:]:
        try:
            old_file.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_cache_files(directory: Path = config.CACHE_DIR, keep: int = config.MAX_CACHE_FILES) -> None:
    """Soft cap on cache size -- prune the least-recently-used entries beyond `keep`."""
    try:
        files = sorted(
            (p for p in directory.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_atime,
            reverse=True,
        )
    except FileNotFoundError:
        return

    for old_file in files[keep:]:
        try:
            old_file.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def cache_key(text: str, voice: str, rate: str, pitch: str, volume: str) -> str:
    raw = f"{voice}|{rate}|{pitch}|{volume}|{text}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# User preferences persistence (simple JSON file, safe for a single bot process)
# ---------------------------------------------------------------------------


def _load_prefs() -> dict[str, Any]:
    if not config.PREFS_FILE.exists():
        return {}
    try:
        with open(config.PREFS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_prefs(data: dict[str, Any]) -> None:
    tmp_path = config.PREFS_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(config.PREFS_FILE)


def get_user_prefs(user_id: int) -> dict[str, Any]:
    data = _load_prefs()
    return data.get(str(user_id), {
        "language": config.DEFAULT_LANGUAGE,
        "gender": config.DEFAULT_GENDER,
        "rate": config.DEFAULT_RATE,
        "pitch": config.DEFAULT_PITCH,
        "volume": config.DEFAULT_VOLUME,
        "auto_detect": True,
    })


def update_user_prefs(user_id: int, **changes: Any) -> dict[str, Any]:
    data = _load_prefs()
    current = data.get(str(user_id), get_user_prefs(user_id))
    current.update(changes)
    data[str(user_id)] = current
    _save_prefs(data)
    return current
