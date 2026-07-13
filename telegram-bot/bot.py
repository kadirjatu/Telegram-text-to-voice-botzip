"""
Main Telegram bot entrypoint.

This is a fresh bot (no pre-existing bot code was found in this project), so
the Text-To-Voice feature is wired in directly here via
`tts.handlers.register_handlers(app)`. If you later add more features, keep
using this same pattern -- build each feature as its own module and register
its handlers here, without touching the others.
"""

from __future__ import annotations

import sys

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import Application, CommandHandler, ContextTypes

from tts import config as tts_config
from tts.handlers import register_handlers
from tts.utils import get_logger

log = get_logger()


def _mini_app_keyboard() -> InlineKeyboardMarkup | None:
    if not tts_config.MINI_APP_URL:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001F5B1 Open Mini App", web_app=WebAppInfo(url=tts_config.MINI_APP_URL))]]
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "\U0001F44B Welcome!\n\n"
        "\U0001F3A4 Text To Voice\n"
        "/tts -- send text and I'll turn it into a voice message\n"
        "/tts <text> -- convert immediately\n"
        "Reply to any text message with /tts to convert it\n\n"
        "/voice -- choose a default language and voice (male/female)\n"
        "/autodetect -- let me detect the language automatically (default)\n"
        "/settings -- adjust rate, pitch and volume\n"
        "/myvoice -- see your current voice settings\n"
        "/app -- open the Text to Voice mini app\n"
        "/cancel -- stop a voice generation in progress\n"
        "/help -- show this message again",
        reply_markup=_mini_app_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command(update, context)


async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = _mini_app_keyboard()
    if keyboard is None:
        await update.effective_message.reply_text(
            "Mini app abhi configure nahi hai (public domain env var missing -- "
            "set RAILWAY_PUBLIC_DOMAIN/REPLIT_DEV_DOMAIN/MINI_APP_PUBLIC_DOMAIN)."
        )
        return
    await update.effective_message.reply_text(
        "Same Text-to-Voice features, ab ek simple app mein:",
        reply_markup=keyboard,
    )


async def _post_init(application: Application) -> None:
    """Sets the persistent Menu Button (the icon next to the message input,
    beside the emoji/attachment icon) to open the Mini App directly --
    the "traditional" way users expect to launch a Telegram Web App."""
    if not tts_config.MINI_APP_URL:
        log.warning("MINI_APP_URL not set; skipping chat menu button setup.")
        return
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Text to Voice",
            web_app=WebAppInfo(url=tts_config.MINI_APP_URL),
        )
    )
    log.info("Chat menu button set to open the Mini App.")


def build_application() -> Application:
    if not tts_config.BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set.")
        sys.exit(
            "TELEGRAM_BOT_TOKEN environment variable is missing. "
            "Set it as a secret and restart the bot."
        )

    app = Application.builder().token(tts_config.BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("app", app_command))

    # Text-To-Voice feature -- fully self-contained inside tts/
    register_handlers(app)

    return app


def main() -> None:
    app = build_application()
    log.info("Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
