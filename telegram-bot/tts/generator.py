"""
Speech generation: Edge-TTS -> MP3 -> FFmpeg -> OGG/Opus (Telegram voice note
format), fully async and never blocking the bot's event loop.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import edge_tts

from . import config, ssml, utils

log = utils.get_logger()


class TTSError(Exception):
    """Base class for all user-facing TTS failures."""


class EmptyTextError(TTSError):
    pass


class EdgeServiceError(TTSError):
    pass


class NetworkError(TTSError):
    pass


class FFmpegMissingError(TTSError):
    pass


class FileCreationError(TTSError):
    pass


class CancelledByUser(TTSError):
    pass


@dataclass
class GeneratedVoice:
    ogg_path: Path
    duration_hint: float
    from_cache: bool


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def _stream_one(text: str, voice: str, rate: str, pitch: str, volume: str, mp3_path: Path) -> None:
    """One Edge-TTS request -> mp3 file. Raises TTSError subclasses on failure."""
    try:
        communicate = edge_tts.Communicate(
            text, voice, rate=rate, pitch=pitch, volume=volume
        )
        wrote_any_audio = False
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                    wrote_any_audio = True
        if not wrote_any_audio:
            raise EdgeServiceError("Edge-TTS returned no audio for this text/voice.")
    except edge_tts.exceptions.NoAudioReceived as exc:
        raise EdgeServiceError("The Edge-TTS service returned no audio.") from exc
    except (edge_tts.exceptions.UnknownResponse, edge_tts.exceptions.UnexpectedResponse) as exc:
        raise EdgeServiceError("The Edge-TTS service returned an unexpected response.") from exc
    except (ConnectionError, OSError, TimeoutError) as exc:
        raise NetworkError("Could not reach the Edge-TTS service (network issue).") from exc
    except asyncio.CancelledError:
        raise CancelledByUser("Generation was cancelled.")
    except Exception as exc:  # last-resort catch so callers always get a TTSError
        raise EdgeServiceError(f"Speech generation failed: {exc}") from exc


async def _concat_with_pauses(part_paths: list[Path], out_path: Path, pause_sec: float = 0.3) -> None:
    """
    Stitch per-sentence mp3s into one file with a short silence gap between
    each, so the voice note breathes at sentence boundaries instead of
    reading everything flat. (edge-tts's free endpoint rejects injected
    <break>/<emphasis> SSML tags outright -- confirmed they come back with
    zero audio -- so this concatenation is the reliable way to get real
    pauses.)
    """
    if len(part_paths) == 1:
        shutil.copyfile(part_paths[0], out_path)
        return

    if not _ffmpeg_available():
        raise FFmpegMissingError(
            "FFmpeg is not installed on the server, so the voice message can't be encoded."
        )

    silence_path = utils.new_temp_path(config.TEMP_DIR, ".silence.mp3")
    inputs = part_paths
    try:
        gen = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", str(round(pause_sec, 3)), "-q:a", "9", str(silence_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, gen_err = await gen.communicate()
        if gen.returncode == 0 and silence_path.exists():
            inputs = []
            for i, p in enumerate(part_paths):
                inputs.append(p)
                if i < len(part_paths) - 1:
                    inputs.append(silence_path)
        else:
            log.warning(
                "Silence-gap generation failed, concatenating without pauses: %s",
                gen_err.decode(errors="ignore")[-200:],
            )

        n = len(inputs)
        filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        args = ["ffmpeg", "-y"]
        for p in inputs:
            args += ["-i", str(p)]
        args += ["-filter_complex", filter_str, "-map", "[out]", str(out_path)]

        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not out_path.exists():
            raise FileCreationError(
                f"FFmpeg failed to stitch sentence pauses together: {stderr.decode(errors='ignore')[-300:]}"
            )
    finally:
        silence_path.unlink(missing_ok=True)


async def _text_to_mp3(text: str, voice: str, rate: str, pitch: str, volume: str, mp3_path: Path, pause_sec: float = 0.3) -> None:
    """
    Generate mp3 audio for `text`. Single-sentence text goes straight
    through one Edge-TTS request exactly as before; multi-sentence text is
    generated sentence-by-sentence and stitched together with short pauses
    for a more natural, less flat-sounding result.
    """
    segments = ssml.split_sentences(text)
    if len(segments) <= 1:
        await _stream_one(text, voice, rate, pitch, volume, mp3_path)
        return

    temp_parts: list[Path] = []
    try:
        for i, segment in enumerate(segments):
            part_path = utils.new_temp_path(config.TEMP_DIR, f".part{i}.mp3")
            await _stream_one(segment, voice, rate, pitch, volume, part_path)
            temp_parts.append(part_path)
        await _concat_with_pauses(temp_parts, mp3_path, pause_sec=pause_sec)
    finally:
        for p in temp_parts:
            p.unlink(missing_ok=True)


async def _mp3_to_ogg_opus(mp3_path: Path, ogg_path: Path) -> None:
    """Convert MP3 -> OGG/Opus (Telegram voice message codec) via ffmpeg."""
    if not _ffmpeg_available():
        raise FFmpegMissingError(
            "FFmpeg is not installed on the server, so the voice message can't be encoded."
        )

    # Light polish pass so the voice note sounds mixed, not raw TTS output:
    # a gentle high-pass to cut rumble, subtle compression to even out
    # loudness, a small presence boost for clarity, and a limiter as a
    # safety ceiling against clipping. Kept gentle on purpose -- the same
    # "too much = artificial" rule applies to processing, not just rate/pitch.
    audio_filters = (
        "highpass=f=80,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=10:release=120:makeup=1.5,"
        "equalizer=f=3000:t=q:w=1:g=2,"
        "alimiter=limit=0.95"
    )

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i", str(mp3_path),
        "-af", audio_filters,
        "-c:a", "libopus",
        "-b:a", "64k",
        "-vbr", "on",
        "-ar", "48000",
        "-ac", "1",
        str(ogg_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0 or not ogg_path.exists():
        raise FileCreationError(
            f"FFmpeg failed to produce the voice file: {stderr.decode(errors='ignore')[-300:]}"
        )


async def generate_voice_note(
    *,
    text: str,
    voice: str,
    rate: str = config.DEFAULT_RATE,
    pitch: str = config.DEFAULT_PITCH,
    volume: str = config.DEFAULT_VOLUME,
    pause_sec: float = 0.3,
    cancel_event: Optional[asyncio.Event] = None,
) -> GeneratedVoice:
    """
    Generate a single Telegram-ready OGG/Opus voice note for `text` (must
    already be within CHUNK_CHAR_LIMIT -- see utils.split_text for longer
    text). Reuses a cached result when the same (text, voice, settings)
    combination was generated before.
    """
    text = (text or "").strip()
    if not text:
        raise EmptyTextError("There is no text to convert.")

    # Meaning-preserving cleanup (spacing/punctuation only) so the sentence
    # flow the SSML pass below builds pauses from is well-formed even if the
    # user's original message wasn't.
    text = ssml.normalize_text(text)

    key = utils.cache_key(text, voice, rate, pitch, volume)
    cached_path = config.CACHE_DIR / f"{key}.ogg"

    if config.CACHE_ENABLED and cached_path.exists():
        cached_path.touch()  # refresh LRU timestamp
        return GeneratedVoice(ogg_path=cached_path, duration_hint=0.0, from_cache=True)

    if cancel_event is not None and cancel_event.is_set():
        raise CancelledByUser("Generation was cancelled before it started.")

    mp3_path = utils.new_temp_path(config.TEMP_DIR, ".mp3")
    ogg_scratch_path = utils.new_temp_path(config.TEMP_DIR, ".ogg")

    start = time.monotonic()
    try:
        tts_task = asyncio.create_task(
            _text_to_mp3(text, voice, rate, pitch, volume, mp3_path, pause_sec=pause_sec)
        )
        if cancel_event is not None:
            cancel_wait = asyncio.create_task(cancel_event.wait())
            done, pending = await asyncio.wait(
                {tts_task, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancel_wait in done and not tts_task.done():
                tts_task.cancel()
                raise CancelledByUser("Generation was cancelled by the user.")
            for p in pending:
                p.cancel()
            tts_task.result()  # re-raise any exception
        else:
            await tts_task

        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            raise FileCreationError("The audio file could not be created.")

        await _mp3_to_ogg_opus(mp3_path, ogg_scratch_path)

        if config.CACHE_ENABLED:
            shutil.copyfile(ogg_scratch_path, cached_path)
            utils.cleanup_cache_files()
            result_path = cached_path
        else:
            result_path = ogg_scratch_path

        elapsed = time.monotonic() - start
        return GeneratedVoice(ogg_path=result_path, duration_hint=elapsed, from_cache=False)
    finally:
        mp3_path.unlink(missing_ok=True)
        if ogg_scratch_path != locals().get("result_path"):
            ogg_scratch_path.unlink(missing_ok=True)
        utils.cleanup_temp_files()
