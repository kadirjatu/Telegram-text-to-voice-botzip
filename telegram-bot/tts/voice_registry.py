"""
Dynamic Edge-TTS voice registry.

Fetches the live Microsoft Edge-TTS voice catalogue ONCE per process on
first use (lazy, async). Filters to Neural-only voices, groups them by
display language name, and picks the best male/female voice per language
using a locale-preference ranking.

Used as the PRIMARY source by voices.voice_for(); the curated LANGUAGES
dict in voices.py remains as a fallback when the registry hasn't loaded
yet or when a network error prevents the live fetch.

Nothing in this file is hardcoded -- if Microsoft adds new voices or new
locales, they appear automatically after the next process restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import edge_tts

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Display-language → locale prefix mapping.
# Every locale whose string starts with any of the listed prefixes is
# treated as a candidate voice for that display name.
# ---------------------------------------------------------------------------
_LOCALE_PREFIX: dict[str, list[str]] = {
    "English":    ["en-"],
    "Hindi":      ["hi-"],
    "Urdu":       ["ur-"],
    "Arabic":     ["ar-"],
    "French":     ["fr-"],
    "Spanish":    ["es-"],
    "Russian":    ["ru-"],
    "Japanese":   ["ja-"],
    "Korean":     ["ko-"],
    "Chinese":    ["zh-"],
    "German":     ["de-"],
    "Italian":    ["it-"],
    "Portuguese": ["pt-"],
    "Turkish":    ["tr-"],
    "Indonesian": ["id-"],
    "Vietnamese": ["vi-"],
    "Thai":       ["th-"],
    "Bengali":    ["bn-"],
    "Tamil":      ["ta-"],
    "Telugu":     ["te-"],
    "Punjabi":    ["pa-"],
    "Gujarati":   ["gu-"],
    "Marathi":    ["mr-"],
    "Malayalam":  ["ml-"],
    "Kannada":    ["kn-"],
}

# Preferred locale per display language (lower rank = more preferred).
# Locales not listed here get rank 999 and are used only as last resort.
_LOCALE_RANK: dict[str, int] = {
    # English
    "en-US": 0, "en-GB": 1, "en-AU": 2, "en-IN": 3,
    # South Asian
    "hi-IN": 0,
    "ur-PK": 0,
    "bn-IN": 0, "bn-BD": 1,
    "ta-IN": 0, "ta-LK": 1, "ta-SG": 2,
    "te-IN": 0,
    "pa-IN": 0, "pa-PK": 1,
    "gu-IN": 0,
    "mr-IN": 0,
    "ml-IN": 0,
    "kn-IN": 0,
    # Middle East
    "ar-SA": 0, "ar-EG": 1, "ar-AE": 2,
    # European
    "fr-FR": 0, "fr-CA": 1, "fr-BE": 2,
    "es-ES": 0, "es-MX": 1, "es-AR": 2,
    "ru-RU": 0,
    "de-DE": 0, "de-AT": 1, "de-CH": 2,
    "it-IT": 0,
    "pt-BR": 0, "pt-PT": 1,
    # East / SE Asian
    "ja-JP": 0,
    "ko-KR": 0,
    "zh-CN": 0, "zh-TW": 1, "zh-HK": 2,
    "tr-TR": 0,
    "id-ID": 0,
    "vi-VN": 0,
    "th-TH": 0,
}

# Words that disqualify a voice (matched case-insensitively against name/status).
_SKIP_WORDS: frozenset[str] = frozenset(["preview", "experimental", "legacy"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_neural(voice: dict) -> bool:
    return "Neural" in (voice.get("ShortName") or "")


def _is_disqualified(voice: dict) -> bool:
    haystack = " ".join(filter(None, [
        voice.get("FriendlyName"),
        voice.get("ShortName"),
        voice.get("Status"),
    ])).lower()
    return any(w in haystack for w in _SKIP_WORDS)


def _display_for_locale(locale: str) -> Optional[str]:
    lower = locale.lower()
    for name, prefixes in _LOCALE_PREFIX.items():
        if any(lower.startswith(p.lower()) for p in prefixes):
            return name
    return None


def _voice_score(voice: dict) -> tuple:
    """
    Lower score = better candidate within a (language, gender) bucket.
    Ranking factors (in priority order):
      1. Preferred locale rank (primary > regional > obscure)
      2. Avoid Multilingual voices (unusual accent / not always stable)
      3. Shorter ShortName as tie-breaker (canonical names tend to be shorter)
    """
    locale = voice.get("Locale") or ""
    rank = _LOCALE_RANK.get(locale, 999)
    short = voice.get("ShortName") or ""
    multilingual = 1 if "Multilingual" in short else 0
    return (rank, multilingual, len(short))


# ---------------------------------------------------------------------------
# Module-level registry state (populated once per process)
# ---------------------------------------------------------------------------
# display_name → {"male": ShortName | None, "female": ShortName | None}
_REGISTRY: dict[str, dict[str, Optional[str]]] = {}
_LOADED: bool = False
_LOCK: Optional[asyncio.Lock] = None


async def _build_registry() -> None:
    global _LOADED
    try:
        all_voices = await edge_tts.list_voices()
    except Exception as exc:
        log.warning(
            "voice_registry: failed to fetch live voice list (%s). "
            "Hardcoded fallback (voices.LANGUAGES) will be used.",
            exc,
        )
        _LOADED = True  # don't retry on every request
        return

    # Bucket by (display_language, gender)
    buckets: dict[str, dict[str, list[dict]]] = {}
    for v in all_voices:
        if not _is_neural(v):
            continue
        if _is_disqualified(v):
            continue
        display = _display_for_locale(v.get("Locale") or "")
        if not display:
            continue
        gender = (v.get("Gender") or "").lower()
        if gender not in ("male", "female"):
            continue
        buckets.setdefault(display, {}).setdefault(gender, []).append(v)

    # Pick the best voice per (language, gender) using the scoring function
    for display, genders in buckets.items():
        _REGISTRY[display] = {}
        for gender, candidates in genders.items():
            best = min(candidates, key=_voice_score)
            _REGISTRY[display][gender] = best["ShortName"]

    _LOADED = True
    found = sorted(_REGISTRY.keys())
    log.info(
        "voice_registry: discovered %d languages from live Edge-TTS catalogue: %s",
        len(found),
        ", ".join(found),
    )


async def ensure_loaded() -> None:
    """
    Idempotent async initialiser.

    Fetches the live Edge-TTS voice catalogue on the FIRST call per process
    and populates the in-memory registry. All subsequent calls return
    immediately (no network request). Safe to call concurrently.
    """
    global _LOCK
    if _LOADED:
        return
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    async with _LOCK:
        if not _LOADED:
            await _build_registry()


# ---------------------------------------------------------------------------
# Public API (called by voices.py)
# ---------------------------------------------------------------------------

def best_voice(language: str, gender: str) -> Optional[str]:
    """
    Return the best dynamically-discovered ShortName for (language, gender).

    Returns None when:
    - The registry hasn't loaded yet (ensure_loaded not awaited yet), OR
    - No Neural voice was found for this language/gender combination.

    Falls back to the other gender within the same language if the exact
    gender isn't available (rare, only affects single-voice languages).
    """
    entry = _REGISTRY.get(language)
    if not entry:
        return None
    result = entry.get(gender.lower())
    if result:
        return result
    # Gender fallback within same language
    for v in entry.values():
        if v:
            return v
    return None


def available_languages() -> list[str]:
    """
    Sorted list of display-language names for which the live registry has
    at least one Neural voice. Empty list when registry hasn't loaded yet.
    """
    return sorted(_REGISTRY.keys())
