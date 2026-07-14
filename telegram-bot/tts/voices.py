"""
Voice catalogue for the Text-To-Voice feature.

All voices are official Microsoft Edge neural voices (used through edge-tts).
No API key, no Azure subscription -- edge-tts simply talks to the same free
service that powers "Read Aloud" in Microsoft Edge.
"""

from __future__ import annotations

from typing import Optional

import edge_tts

# ---------------------------------------------------------------------------
# Curated language -> {male, female} voice map.
#
# Every short-name below was verified against the live `edge_tts.list_voices()`
# catalogue. Punjabi is intentionally excluded: Microsoft Edge TTS currently
# ships no Punjabi neural voice, so we don't fake one -- see `voice_for`.
# ---------------------------------------------------------------------------
LANGUAGES: dict[str, dict[str, str]] = {
    "English":    {"locale": "en-US", "male": "en-US-AndrewNeural",  "female": "en-US-AvaNeural"},
    "Hindi":      {"locale": "hi-IN", "male": "hi-IN-MadhurNeural",  "female": "hi-IN-SwaraNeural"},
    "Urdu":       {"locale": "ur-PK", "male": "ur-PK-AsadNeural",    "female": "ur-PK-UzmaNeural"},
    "Arabic":     {"locale": "ar-SA", "male": "ar-SA-HamedNeural",   "female": "ar-SA-ZariyahNeural"},
    "French":     {"locale": "fr-FR", "male": "fr-FR-HenriNeural",   "female": "fr-FR-DeniseNeural"},
    "Spanish":    {"locale": "es-ES", "male": "es-ES-AlvaroNeural",  "female": "es-ES-ElviraNeural"},
    "Russian":    {"locale": "ru-RU", "male": "ru-RU-DmitryNeural",  "female": "ru-RU-SvetlanaNeural"},
    "Japanese":   {"locale": "ja-JP", "male": "ja-JP-KeitaNeural",   "female": "ja-JP-NanamiNeural"},
    "Korean":     {"locale": "ko-KR", "male": "ko-KR-InJoonNeural",  "female": "ko-KR-SunHiNeural"},
    "Chinese":    {"locale": "zh-CN", "male": "zh-CN-YunxiNeural",   "female": "zh-CN-XiaoxiaoNeural"},
    "German":     {"locale": "de-DE", "male": "de-DE-ConradNeural",  "female": "de-DE-KatjaNeural"},
    "Italian":    {"locale": "it-IT", "male": "it-IT-DiegoNeural",   "female": "it-IT-ElsaNeural"},
    "Portuguese": {"locale": "pt-BR", "male": "pt-BR-AntonioNeural", "female": "pt-BR-FranciscaNeural"},
    "Turkish":    {"locale": "tr-TR", "male": "tr-TR-AhmetNeural",   "female": "tr-TR-EmelNeural"},
    "Indonesian": {"locale": "id-ID", "male": "id-ID-ArdiNeural",    "female": "id-ID-GadisNeural"},
    "Vietnamese": {"locale": "vi-VN", "male": "vi-VN-NamMinhNeural", "female": "vi-VN-HoaiMyNeural"},
    "Thai":       {"locale": "th-TH", "male": "th-TH-NiwatNeural",   "female": "th-TH-PremwadeeNeural"},
    "Bengali":    {"locale": "bn-IN", "male": "bn-IN-BashkarNeural", "female": "bn-IN-TanishaaNeural"},
    "Tamil":      {"locale": "ta-IN", "male": "ta-IN-ValluvarNeural","female": "ta-IN-PallaviNeural"},
    "Telugu":     {"locale": "te-IN", "male": "te-IN-MohanNeural",   "female": "te-IN-ShrutiNeural"},
    "Gujarati":   {"locale": "gu-IN", "male": "gu-IN-NiranjanNeural","female": "gu-IN-DhwaniNeural"},
    "Marathi":    {"locale": "mr-IN", "male": "mr-IN-ManoharNeural", "female": "mr-IN-AarohiNeural"},
    "Malayalam":  {"locale": "ml-IN", "male": "ml-IN-MidhunNeural",  "female": "ml-IN-SobhanaNeural"},
    "Kannada":    {"locale": "kn-IN", "male": "kn-IN-GaganNeural",   "female": "kn-IN-SapnaNeural"},
}

# Punjabi is on the requested list but has no Edge-TTS neural voice today.
# We surface it in the menu with a clear notice instead of silently
# substituting another language's voice.
UNSUPPORTED_LANGUAGES: dict[str, str] = {
    "Punjabi": "Microsoft Edge TTS has no Punjabi voice yet. Try Hindi or Urdu instead.",
}

# langdetect ISO 639-1 / locale codes -> our language keys, for auto-detection.
_LANGDETECT_MAP: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ur": "Urdu",
    "ar": "Arabic",
    "fr": "French",
    "es": "Spanish",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "tr": "Turkish",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "th": "Thai",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "gu": "Gujarati",
    "mr": "Marathi",
    "ml": "Malayalam",
    "kn": "Kannada",
}


def detect_language(text: str) -> Optional[str]:
    """Best-effort language auto-detection. Returns a key in LANGUAGES, or None."""
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0  # deterministic results
        code = detect(text).lower()
    except Exception:
        return None
    return _LANGDETECT_MAP.get(code)


def voice_for(language: str, gender: str) -> Optional[str]:
    """Return the Edge-TTS short voice name for a language + gender pair."""
    # Try the live dynamic registry first (no hardcoded IDs).
    from . import voice_registry
    reg = voice_registry.best_voice(language, gender)
    if reg:
        return reg
    # Fall back to the curated LANGUAGES dict (covers the case where the
    # registry hasn't loaded yet or the network was unavailable on startup).
    entry = LANGUAGES.get(language)
    if not entry:
        return None
    return entry.get(gender.lower())


def language_list() -> list[str]:
    """All selectable (supported) language names, alphabetically sorted.

    Merges the hardcoded LANGUAGES dict with the live registry so that:
    - New Microsoft voices are discovered automatically after restart.
    - Languages in UNSUPPORTED_LANGUAGES (e.g. Punjabi) are promoted to
      the supported list as soon as the registry finds a voice for them.
    """
    from . import voice_registry
    combined = set(LANGUAGES.keys()) | set(voice_registry.available_languages())
    # Keep a language in the "unsupported" bucket only if the live registry
    # also has no voice for it.
    still_unsupported = {
        lang for lang in UNSUPPORTED_LANGUAGES
        if voice_registry.best_voice(lang, "female") is None
        and voice_registry.best_voice(lang, "male") is None
    }
    return sorted(combined - still_unsupported)


async def get_available_voices() -> list[dict]:
    """
    Helper required by spec: returns the full list of official Edge voices
    as reported live by the edge-tts service (no API key needed).

    Each item looks like:
        {"ShortName": "en-US-AriaNeural", "Gender": "Female", "Locale": "en-US", ...}
    """
    return await edge_tts.list_voices()
