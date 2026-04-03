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
            "Tap Start anytime to return to the main menu.",
            "",
            "In private chats, /start also reopens the menu if needed.",
            "",
            "Admin actions remain available from the lower menu rows.",
        ]
    )


async def ensure_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = get_settings(context)
    user = update.effective_user
    if user is None or user.id not in settings.admin_telegram_user_ids:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Admin access is required for this action.")
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_home_screen(update, context)


async def send_home_screen(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    prefix: str | None = None,
) -> None:
    if update.effective_message is not None:
        lines = ["Song Vault is ready.", "Use the menu buttons below."]
        if prefix:
            lines.insert(0, prefix)
        await update.effective_message.reply_text(
            "\n".join(lines),
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
