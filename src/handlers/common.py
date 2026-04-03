import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.runtime import get_settings
from handlers.ui import home_menu_markup

logger = logging.getLogger(__name__)


def help_text() -> str:
    return "\n".join(
        [
            "Song Vault menu:",
            "Use the on-screen buttons for day-to-day navigation.",
            "",
            "Commands (fallback):",
            "/songs - list active songs",
            "/search <text> - search by title, source, or tag",
            "/addsong - guided song creation",
            "/editsong <id> - guided song update",
            "/archivesong <id> - archive a song",
            "/tags - list known tags",
            "/uploadchart <song_id> - upload or replace a chart image (admin only)",
            "/chart <song_id> - fetch the current chart image",
            "/exportbackup - export repertoire backup (admin only)",
            "/importbackup - import repertoire backup (admin only)",
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
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Song Vault is ready.\nUse the menu buttons below, or /help for command fallback.",
            reply_markup=home_menu_markup(update, context),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            help_text(),
            reply_markup=home_menu_markup(update, context),
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text("The bot hit an unexpected error.")
