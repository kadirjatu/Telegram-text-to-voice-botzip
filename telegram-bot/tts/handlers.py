"""
Telegram command / message / callback handlers for the Text-To-Voice feature.

Works in private chats, groups, and supergroups. Nothing here touches or
imports the rest of your existing bot -- register `register_handlers(app)`
from your main bot file and this feature is fully wired in.
"""

from __future__ import annotations

import asyncio
import html

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, generator, translator, utils, voices

log = utils.get_logger()

# In-memory per (chat_id, user_id) state. Small and process-local by design --
# if the bot restarts, users just re-run /tts.
_AWAITING_TEXT: set[tuple[int, int]] = set()
_ACTIVE_CANCEL_EVENTS: dict[tuple[int, int], asyncio.Event] = {}

# Holds the text waiting for a language + gender pick, keyed by (chat_id, user_id).
# Every /tts request goes through this -- we always ask, we never silently
# reuse the saved default voice for the actual conversion.
_PENDING: dict[tuple[int, int], dict] = {}


def _state_key(update: Update) -> tuple[int, int]:
    chat = update.effective_chat
    user = update.effective_user
    return (chat.id if chat else 0, user.id if user else 0)


# ---------------------------------------------------------------------------
# /tts
# ---------------------------------------------------------------------------


async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    key = _state_key(update)

    direct_text = " ".join(context.args) if context.args else ""

    if not direct_text and message.reply_to_message and message.reply_to_message.text:
        direct_text = message.reply_to_message.text

    if direct_text:
        _AWAITING_TEXT.discard(key)
        await _start_voice_selection(update, context, direct_text)
        return

    _AWAITING_TEXT.add(key)
    await message.reply_text("Send me the text you want to convert into speech.")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = _state_key(update)
    _AWAITING_TEXT.discard(key)
    event = _ACTIVE_CANCEL_EVENTS.get(key)
    if event is not None:
        event.set()
        await update.effective_message.reply_text("Cancelling your voice request...")
    else:
        await update.effective_message.reply_text("There is nothing to cancel right now.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the plain-text reply that follows a bare /tts."""
    key = _state_key(update)
    if key not in _AWAITING_TEXT:
        return  # not something this feature should react to

    _AWAITING_TEXT.discard(key)
    await _start_voice_selection(update, context, update.effective_message.text or "")


# ---------------------------------------------------------------------------
# Language + gender picker -- asked on every /tts request, before generating.
# ---------------------------------------------------------------------------


async def _start_voice_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    message = update.effective_message
    key = _state_key(update)
    text = text.strip()

    if not text:
        await message.reply_text("That message had no text in it, so there's nothing to convert.")
        return

    if len(text) > config.MAX_TOTAL_CHAR_LIMIT:
        await message.reply_text(
            f"That's too long ({len(text)} characters). Please send up to "
            f"{config.MAX_TOTAL_CHAR_LIMIT} characters at a time."
        )
        return

    _PENDING[key] = {"text": text}
    await message.reply_text(
        "Is text ke liye language chuno (ya Auto-detect):",
        reply_markup=_flow_language_keyboard(),
    )


def _flow_language_keyboard() -> InlineKeyboardMarkup:
    names = voices.language_list()
    rows = [[InlineKeyboardButton("\U0001F310 Auto-detect", callback_data="ftl:auto")]]
    rows += [
        [InlineKeyboardButton(names[i], callback_data=f"ftl:{names[i]}")]
        + (
            [InlineKeyboardButton(names[i + 1], callback_data=f"ftl:{names[i + 1]}")]
            if i + 1 < len(names)
            else []
        )
        for i in range(0, len(names), 2)
    ]
    for name in voices.UNSUPPORTED_LANGUAGES:
        rows.append([InlineKeyboardButton(f"{name} (limited)", callback_data=f"ftlx:{name}")])
    return InlineKeyboardMarkup(rows)


def _flow_gender_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{language} Male", callback_data="ftg:male"),
                InlineKeyboardButton(f"{language} Female", callback_data="ftg:female"),
            ]
        ]
    )


async def flow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the language/gender buttons shown before every conversion."""
    query = update.callback_query
    await query.answer()
    key = _state_key(update)
    data = query.data
    pending = _PENDING.get(key)

    if data.startswith("ftlx:"):
        language = data.split(":", 1)[1]
        note = voices.UNSUPPORTED_LANGUAGES.get(language, "This language isn't available yet.")
        await query.edit_message_text(
            f"{html.escape(language)}: {note}\nKisi doosri language ke liye /tts dobara try karo."
        )
        return

    if pending is None:
        await query.edit_message_text("Yeh request expire ho gayi hai. /tts se dobara try karo.")
        return

    if data == "ftl:auto":
        detected = voices.detect_language(pending["text"]) or config.DEFAULT_LANGUAGE
        pending["language"] = detected
        await query.edit_message_text(
            f"Language auto-detect: {detected}\nAb voice chuno:",
            reply_markup=_flow_gender_keyboard(detected),
        )
        return

    if data.startswith("ftl:"):
        language = data.split(":", 1)[1]
        pending["language"] = language
        await query.edit_message_text(
            f"{language} ke liye voice chuno:", reply_markup=_flow_gender_keyboard(language)
        )
        return

    if data.startswith("ftg:"):
        _, gender = data.split(":", 1)
        language = pending.get("language")
        text = pending.get("text")
        _PENDING.pop(key, None)

        if not language or not text:
            await query.edit_message_text("Kuch gadbad ho gayi, /tts se dobara try karo.")
            return

        voice = voices.voice_for(language, gender)
        if not voice:
            await query.edit_message_text(f"{language} {gender} ke liye voice available nahi hai.")
            return

        await query.edit_message_text(f"\u2705 {language} {gender.capitalize()} -- generating...")
        await _run_tts(update, context, text, voice_override=voice, language_label=language)
        return


# ---------------------------------------------------------------------------
# Core generation flow (shared by direct text, reply text, and follow-up text)
# ---------------------------------------------------------------------------


async def _run_tts(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    voice_override: str | None = None,
    language_label: str | None = None,
) -> None:
    message = update.effective_message
    user = update.effective_user
    key = _state_key(update)
    text = text.strip()

    if not text:
        await message.reply_text("That message had no text in it, so there's nothing to convert.")
        return

    if len(text) > config.MAX_TOTAL_CHAR_LIMIT:
        await message.reply_text(
            f"That's too long ({len(text)} characters). Please send up to "
            f"{config.MAX_TOTAL_CHAR_LIMIT} characters at a time."
        )
        return

    prefs = utils.get_user_prefs(user.id)

    if voice_override:
        voice = voice_override
        language = language_label
    else:
        # Fallback path (kept for any future caller that already knows the
        # voice it wants, e.g. the mini app). The Telegram bot flow above
        # always supplies voice_override -- it never reaches this branch.
        language = prefs.get("language", config.DEFAULT_LANGUAGE)
        if prefs.get("auto_detect", True):
            detected = voices.detect_language(text)
            if detected:
                language = detected
        voice = voices.voice_for(language, prefs.get("gender", config.DEFAULT_GENDER))
        if not voice:
            voice = voices.voice_for(config.DEFAULT_LANGUAGE, config.DEFAULT_GENDER)

    # The spoken output must actually be in the chosen language, not just the
    # original words read with that language's accent -- translate first.
    if language:
        text = translator.translate_text(text, language)

    chunks = utils.split_text(text)
    if not chunks:
        await message.reply_text("That message had no text in it, so there's nothing to convert.")
        return

    cancel_event = asyncio.Event()
    _ACTIVE_CANCEL_EVENTS[key] = cancel_event

    status_message = await message.reply_text("\U0001F3A4 Generating Voice...")

    try:
        for index, chunk in enumerate(chunks, start=1):
            if cancel_event.is_set():
                raise generator.CancelledByUser("Cancelled by user.")

            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.RECORD_VOICE)

            try:
                result = await generator.generate_voice_note(
                    text=chunk,
                    voice=voice,
                    rate=prefs.get("rate", config.DEFAULT_RATE),
                    pitch=prefs.get("pitch", config.DEFAULT_PITCH),
                    volume=prefs.get("volume", config.DEFAULT_VOLUME),
                    cancel_event=cancel_event,
                )
            except generator.CancelledByUser:
                raise
            except generator.EmptyTextError:
                continue
            except generator.FFmpegMissingError as exc:
                utils.log_error(user.id, str(exc))
                await status_message.edit_text(f"\u274C Server error: {exc}")
                return
            except generator.NetworkError as exc:
                utils.log_error(user.id, str(exc))
                await status_message.edit_text(f"\u274C Network problem, please try again: {exc}")
                return
            except generator.EdgeServiceError as exc:
                utils.log_error(user.id, str(exc))
                await status_message.edit_text(f"\u274C Edge-TTS service is unavailable right now: {exc}")
                return
            except generator.FileCreationError as exc:
                utils.log_error(user.id, str(exc))
                await status_message.edit_text(f"\u274C Could not create the audio file: {exc}")
                return

            caption = None
            if len(chunks) > 1:
                caption = f"Part {index}/{len(chunks)}"

            try:
                with open(result.ogg_path, "rb") as audio_file:
                    await context.bot.send_voice(
                        chat_id=message.chat_id,
                        voice=audio_file,
                        caption=caption,
                        reply_to_message_id=message.message_id if index == 1 else None,
                    )
            except TimeoutError as exc:
                utils.log_error(user.id, f"telegram timeout: {exc}")
                await status_message.edit_text("\u274C Telegram timed out sending the voice message. Please try again.")
                return
            except Exception as exc:
                utils.log_error(user.id, f"telegram send failed: {exc}")
                await status_message.edit_text(f"\u274C Could not send the voice message: {exc}")
                return

            utils.log_request(user.id, voice, len(chunk), result.duration_hint)

        await status_message.edit_text("\u2705 Voice Generated Successfully")

    except generator.CancelledByUser:
        await status_message.edit_text("\U0001F6D1 Voice generation cancelled.")
    except Exception as exc:  # last-resort safety net -- the bot must never crash
        utils.log_error(user.id, f"unexpected error: {exc}")
        await status_message.edit_text("\u274C Something went wrong while generating the voice message.")
    finally:
        _ACTIVE_CANCEL_EVENTS.pop(key, None)


# ---------------------------------------------------------------------------
# /voice -- language + gender picker
# ---------------------------------------------------------------------------


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Choose a language for your voice:",
        reply_markup=_language_keyboard(),
    )


def _language_keyboard() -> InlineKeyboardMarkup:
    names = voices.language_list()
    rows = [
        [InlineKeyboardButton(names[i], callback_data=f"tts_lang:{names[i]}")]
        + (
            [InlineKeyboardButton(names[i + 1], callback_data=f"tts_lang:{names[i + 1]}")]
            if i + 1 < len(names)
            else []
        )
        for i in range(0, len(names), 2)
    ]
    for name in voices.UNSUPPORTED_LANGUAGES:
        rows.append([InlineKeyboardButton(f"{name} (limited)", callback_data=f"tts_lang_unsupported:{name}")])
    return InlineKeyboardMarkup(rows)


def _gender_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{language} Male", callback_data=f"tts_gender:{language}:male"),
                InlineKeyboardButton(f"{language} Female", callback_data=f"tts_gender:{language}:female"),
            ]
        ]
    )


async def voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if data.startswith("tts_lang_unsupported:"):
        language = data.split(":", 1)[1]
        note = voices.UNSUPPORTED_LANGUAGES.get(language, "This language isn't available yet.")
        await query.edit_message_text(f"{html.escape(language)}: {note}")
        return

    if data.startswith("tts_lang:"):
        language = data.split(":", 1)[1]
        await query.edit_message_text(
            f"Pick a voice for {language}:", reply_markup=_gender_keyboard(language)
        )
        return

    if data.startswith("tts_gender:"):
        _, language, gender = data.split(":", 2)
        utils.update_user_prefs(user.id, language=language, gender=gender, auto_detect=False)
        await query.edit_message_text(
            f"\u2705 Voice set to {language} {gender.capitalize()}. Use /tts to try it, "
            f"or /voice again anytime to change it, or turn auto-detect back on with /autodetect."
        )
        return


async def autodetect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    utils.update_user_prefs(user.id, auto_detect=True)
    await update.effective_message.reply_text(
        "\u2705 Auto language detection is back on. I'll pick the voice's language automatically from your text."
    )


async def myvoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prefs = utils.get_user_prefs(update.effective_user.id)
    mode = "auto-detect" if prefs.get("auto_detect", True) else "manual"
    await update.effective_message.reply_text(
        "Your current voice settings:\n"
        f"Language mode: {mode}\n"
        f"Language: {prefs.get('language')}\n"
        f"Gender: {prefs.get('gender')}\n"
        f"Rate: {prefs.get('rate')}\n"
        f"Pitch: {prefs.get('pitch')}\n"
        f"Volume: {prefs.get('volume')}"
    )


# ---------------------------------------------------------------------------
# /settings -- rate / pitch / volume picker
# ---------------------------------------------------------------------------


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Adjust your voice settings:", reply_markup=_settings_keyboard()
    )


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Rate", callback_data="tts_settings_menu:rate")],
            [InlineKeyboardButton("Pitch", callback_data="tts_settings_menu:pitch")],
            [InlineKeyboardButton("Volume", callback_data="tts_settings_menu:volume")],
            [InlineKeyboardButton("Reset to defaults", callback_data="tts_settings_reset")],
        ]
    )


def _options_keyboard(kind: str, options: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt, callback_data=f"tts_set:{kind}:{opt}") for opt in options]]
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if data == "tts_settings_reset":
        utils.update_user_prefs(
            user.id,
            rate=config.DEFAULT_RATE,
            pitch=config.DEFAULT_PITCH,
            volume=config.DEFAULT_VOLUME,
        )
        await query.edit_message_text("\u2705 Rate, pitch, and volume reset to defaults.")
        return

    if data.startswith("tts_settings_menu:"):
        kind = data.split(":", 1)[1]
        options = {
            "rate": config.RATE_OPTIONS,
            "pitch": config.PITCH_OPTIONS,
            "volume": config.VOLUME_OPTIONS,
        }[kind]
        await query.edit_message_text(
            f"Choose {kind}:", reply_markup=_options_keyboard(kind, options)
        )
        return

    if data.startswith("tts_set:"):
        _, kind, value = data.split(":", 2)
        utils.update_user_prefs(user.id, **{kind: value})
        await query.edit_message_text(f"\u2705 {kind.capitalize()} set to {value}.")
        return


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_handlers(app: Application) -> None:
    """Call this once from your existing bot's setup code to add the /tts feature."""
    app.add_handler(CommandHandler("tts", tts_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("autodetect", autodetect_command))
    app.add_handler(CommandHandler("myvoice", myvoice_command))
    app.add_handler(CommandHandler("settings", settings_command))

    app.add_handler(CallbackQueryHandler(voice_callback, pattern=r"^tts_(lang|gender)"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^tts_(settings|set)"))
    app.add_handler(CallbackQueryHandler(flow_callback, pattern=r"^ft"))

    # Bare-/tts follow-up text. group=1 keeps this from clashing with any
    # other text handler your existing bot may already register in group=0.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message), group=1
    )
