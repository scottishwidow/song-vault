import logging

from telegram import Update
from telegram.ext import ContextTypes

from song_vault.bot.runtime import get_settings

logger = logging.getLogger(__name__)


def help_text() -> str:
    return "\n".join(
        [
            "Song Vault commands:",
            "/songs - list active songs",
            "/search <text> - search by title, source, or tag",
            "/addsong - guided song creation",
            "/editsong <id> - guided song update",
            "/archivesong <id> - archive a song",
            "/tags - list known tags",
        ]
    )


async def ensure_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = get_settings(context)
    user = update.effective_user
    if user is None or user.id not in settings.admin_telegram_user_ids:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Admin access is required for this command.")
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Song Vault is ready.\nUse /help to view repertoire commands."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(help_text())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text("The bot hit an unexpected error.")
