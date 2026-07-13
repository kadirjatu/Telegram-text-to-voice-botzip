"""
Text translation so the spoken output actually matches the language the
user picked -- not just an accent applied to the original words.

Uses Google Translate's free web endpoint (via `deep-translator`), same
"no API key needed" spirit as edge-tts.
"""

from __future__ import annotations

from . import utils

log = utils.get_logger()

# Our language names -> Google Translate language codes.
TRANSLATE_CODES: dict[str, str] = {
    "English": "en",
    "Hindi": "hi",
    "Urdu": "ur",
    "Arabic": "ar",
    "French": "fr",
    "Spanish": "es",
    "Russian": "ru",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese": "zh-CN",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Turkish": "tr",
    "Indonesian": "id",
    "Vietnamese": "vi",
    "Thai": "th",
    "Bengali": "bn",
    "Tamil": "ta",
    "Telugu": "te",
    "Gujarati": "gu",
    "Marathi": "mr",
    "Malayalam": "ml",
    "Kannada": "kn",
}


# Languages whose script is not Latin. Used to catch a real Google Translate
# quirk: romanized text (e.g. "Hinglish" -- Hindi typed in Latin letters,
# extremely common) often gets auto-detected AS the target language already,
# so the "auto" translation is skipped entirely and the Latin text comes back
# unchanged -- edge-tts then just reads the Latin letters phonetically,
# which is exactly the "only the accent changes" bug this exists to fix.
_NON_LATIN_TARGET_LANGUAGES = {
    "Hindi", "Urdu", "Arabic", "Russian", "Japanese", "Korean", "Chinese",
    "Bengali", "Tamil", "Telugu", "Gujarati", "Marathi", "Malayalam",
    "Kannada", "Thai",
}


def _has_native_script(text: str) -> bool:
    """True if `text` contains any character outside the Latin/ASCII range."""
    return any(ord(ch) >= 0x0400 for ch in text)


def translate_text(text: str, target_language: str) -> str:
    """
    Translate `text` into `target_language` (auto-detecting the source
    language). Returns the original text unchanged if the target language
    is unknown or the translation service fails -- callers still get a
    voice note instead of a hard error.
    """
    target_code = TRANSLATE_CODES.get(target_language)
    if not target_code:
        return text

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="auto", target=target_code).translate(text)
        translated = translated or text

        needs_native_script = target_language in _NON_LATIN_TARGET_LANGUAGES
        if needs_native_script and not _has_native_script(translated):
            # "auto" likely misdetected romanized input as already being the
            # target language and skipped translation. Forcing an English
            # source makes Google actually translate/transliterate it.
            forced = GoogleTranslator(source="en", target=target_code).translate(text)
            if forced and _has_native_script(forced):
                translated = forced

        return translated
    except Exception as exc:  # translation is best-effort, never fatal
        log.warning("Translation to %s failed, using original text: %s", target_language, exc)
        return text
