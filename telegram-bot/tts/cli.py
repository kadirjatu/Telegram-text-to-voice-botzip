"""
Thin CLI bridge so a non-Python caller (the mini app's Node/Express backend)
can reuse this exact same TTS pipeline -- same voices, same cache, same
error handling as the Telegram bot -- instead of a second implementation.

Usage:
    python -m tts.cli languages
    python -m tts.cli generate      (reads a JSON object from stdin)

Both commands print a single JSON line to stdout and exit 0 on success.
"""

from __future__ import annotations

import asyncio
import json
import sys

from . import config, generator, translator, voices


def _cmd_languages() -> dict:
    return {
        "languages": voices.language_list(),
        "unsupported": voices.UNSUPPORTED_LANGUAGES,
        "defaultLanguage": config.DEFAULT_LANGUAGE,
        "defaultGender": config.DEFAULT_GENDER,
    }


async def _cmd_generate(payload: dict) -> dict:
    text = (payload.get("text") or "").strip()
    raw_language = payload.get("language") or "auto"
    gender = (payload.get("gender") or config.DEFAULT_GENDER).lower()

    # Auto-detect: try to detect language from text, fall back to default.
    if raw_language == "auto":
        detected = voices.detect_language(text)
        language = detected or config.DEFAULT_LANGUAGE
    else:
        language = raw_language
    rate = payload.get("rate") or config.DEFAULT_RATE
    pitch = payload.get("pitch") or config.DEFAULT_PITCH
    volume = payload.get("volume") or config.DEFAULT_VOLUME

    # Urdu-specific defaults: only applied when the caller did not explicitly
    # send these values (bot path -- mini-app sends them from the UI).
    if language == "Urdu":
        if not payload.get("rate"):
            rate = "-5%"
        if not payload.get("pitch"):
            pitch = "+0Hz"
        if not payload.get("volume"):
            volume = "+0%"

    if not text:
        return {"ok": False, "error": "empty_text"}

    if len(text) > config.CHUNK_CHAR_LIMIT:
        return {"ok": False, "error": "too_long", "limit": config.CHUNK_CHAR_LIMIT}

    if language in voices.UNSUPPORTED_LANGUAGES:
        return {"ok": False, "error": "voice_not_available"}

    voice = voices.voice_for(language, gender)
    if not voice:
        return {"ok": False, "error": "voice_not_available"}

    # Match the bot: the spoken output must be in the chosen language, not
    # just the original words read with that language's accent.
    text = translator.translate_text(text, language)

    # Urdu gets a slightly longer inter-sentence pause (400 ms) for a more
    # natural, human-like cadence. All other languages keep the default 300 ms.
    pause_sec = 0.4 if language == "Urdu" else 0.3

    try:
        result = await generator.generate_voice_note(
            text=text, voice=voice, rate=rate, pitch=pitch, volume=volume,
            pause_sec=pause_sec,
        )
    except generator.TTSError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "path": str(result.ogg_path),
        "language": language,
        "gender": gender,
        "voice": voice,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing_command"}))
        sys.exit(1)

    command = sys.argv[1]

    if command == "languages":
        print(json.dumps(_cmd_languages()))
        return

    if command == "generate":
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "invalid_json"}))
            sys.exit(1)
        result = asyncio.run(_cmd_generate(payload))
        print(json.dumps(result))
        return

    print(json.dumps({"ok": False, "error": f"unknown_command:{command}"}))
    sys.exit(1)


if __name__ == "__main__":
    main()
