import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.runtime import get_settings
from handlers.ui import home_menu_markup

logger = logging.getLogger(__name__)


def help_text() -> str:
    return "\n".join(
        [
            "Меню бота:",
            "Для щоденної навігації використовуйте кнопки на екрані.",
            "Натискайте «Головна», щоб повернутися в головне меню.",
            "",
            "У приватних чатах команда /start також знову відкриває меню.",
            "",
            "Дії адміністратора доступні в нижніх рядках меню.",
        ]
    )


async def ensure_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = get_settings(context)
    user = update.effective_user
    if user is None or user.id not in settings.admin_telegram_user_ids:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Для цієї дії потрібні права адміністратора.")
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
        lines = ["Бот готовий.", "Користуйтеся кнопками меню нижче."]
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
        await update.effective_message.reply_text("У боті сталася непередбачена помилка.")
