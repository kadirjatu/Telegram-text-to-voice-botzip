"""
Lightweight SSML enhancement for more natural-sounding speech.

edge-tts's public `Communicate()` API XML-escapes whatever text you give it
before embedding it in the outbound SSML, so literal `<break/>` or
`<emphasis>` tags typed as plain text would just show up escaped -- they'd
never reach the speech service as real markup. This module builds a real
SSML fragment (sentence/clause pauses + optional emphasis) and swaps it into
`Communicate`'s already-public `.texts` attribute, which is exactly what its
own `stream()` loop reads from -- composition through a documented public
attribute, not a rewrite of edge-tts internals.

Only applied when the fragment is small enough to safely fit in a single
edge-tts request (see MAX_SSML_BYTES); longer text falls back to the
existing plain-text path untouched, so this can never risk corrupting SSML
by splitting a tag in half.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

# edge-tts itself caps a single request at 4096 bytes of escaped text (see
# `edge_tts.communicate.Communicate.__init__`). Stay well under that so our
# added <break>/<emphasis> tags never push a request over the real limit.
MAX_SSML_BYTES = 3500

_SENTENCE_BREAK = '<break time="300ms"/>'
_COMMA_BREAK = '<break time="150ms"/>'

# *word* -> emphasized word (intuitive, opt-in -- text without asterisks is
# completely unaffected).
_EMPHASIS_RE = re.compile(r"\*([^*]+)\*")
# Sentence enders, including Hindi/Urdu's danda (।) and Urdu question mark (؟).
_SENTENCE_END_RE = re.compile(r"([.!?\u0964\u061F]+)(\s+|$)")
_COMMA_RE = re.compile(r"(,)(\s+)")

_BREAK_S = "\u0000BREAK_S\u0000"
_BREAK_C = "\u0000BREAK_C\u0000"


def normalize_text(text: str) -> str:
    """
    Light, meaning-preserving cleanup so punctuation reads naturally:
    collapse repeated whitespace and make sure there is a single space after
    commas/periods/etc. when the writer forgot one. Never reorders or drops
    words -- just spacing.
    """
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([,.!?\u0964])(?=[^\s\"'\u0964])", r"\1 ", text)
    return text


def _split_on_punctuation(chunk: str) -> list[str]:
    chunk = _SENTENCE_END_RE.sub(lambda m: f"{m.group(1)}{_BREAK_S}{m.group(2)}", chunk)
    chunk = _COMMA_RE.sub(lambda m: f"{m.group(1)}{_BREAK_C}", chunk)
    return re.split(f"({_BREAK_S}|{_BREAK_C})", chunk)


def build_ssml_fragment(text: str) -> str:
    """
    Turn plain (already-translated) text into an SSML fragment with natural
    pauses at sentence/clause boundaries and optional emphasis on
    *word*-wrapped phrases. Everything except our own tags is XML-escaped,
    so user text can never inject arbitrary markup.
    """
    raw_parts: list[tuple[str, str]] = []
    last = 0
    for match in _EMPHASIS_RE.finditer(text):
        raw_parts.append(("text", text[last:match.start()]))
        raw_parts.append(("emphasis", match.group(1)))
        last = match.end()
    raw_parts.append(("text", text[last:]))

    pieces: list[str] = []
    for kind, chunk in raw_parts:
        if not chunk:
            continue
        if kind == "emphasis":
            stripped = chunk.strip()
            if stripped:
                pieces.append(f'<emphasis level="moderate">{escape(stripped)}</emphasis>')
            continue

        for seg in _split_on_punctuation(chunk):
            if seg == _BREAK_S:
                pieces.append(_SENTENCE_BREAK)
            elif seg == _BREAK_C:
                pieces.append(_COMMA_BREAK)
            elif seg:
                pieces.append(escape(seg))

    return "".join(pieces)


def fits_single_request(ssml_fragment: str) -> bool:
    """Whether the fragment is safely below edge-tts's per-request byte cap."""
    return len(ssml_fragment.encode("utf-8")) <= MAX_SSML_BYTES


def split_sentences(text: str) -> list[str]:
    """
    Split into sentence-ish segments on strong sentence enders (., !, ?, the
    Hindi/Urdu danda \u0964, and Urdu's \u061F). Used to generate natural
    inter-sentence pauses by stitching separately-generated audio together
    (see generator.py) -- edge-tts's free endpoint rejects injected
    <break>/<emphasis> SSML tags outright, so this is the reliable
    alternative. *word* emphasis markers are stripped (just the asterisks --
    real emphasis markup isn't achievable through this endpoint).
    """
    text = _EMPHASIS_RE.sub(lambda m: m.group(1), text)

    segments: list[str] = []
    last = 0
    for match in _SENTENCE_END_RE.finditer(text):
        piece = text[last:match.end()].strip()
        if piece:
            segments.append(piece)
        last = match.end()
    tail = text[last:].strip()
    if tail:
        segments.append(tail)
    return segments or ([text.strip()] if text.strip() else [])
