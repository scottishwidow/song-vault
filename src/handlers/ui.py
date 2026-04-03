from __future__ import annotations

from collections.abc import Sequence

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.runtime import get_settings

MENU_SONGS = "Songs"
MENU_SEARCH = "Search"
MENU_TAGS = "Tags"
MENU_HELP = "Help"
MENU_ADD_SONG = "Add Song"
MENU_UPLOAD_CHART = "Upload Chart"
MENU_BACKUP = "Backup"

BUTTON_SKIP = "Skip"
BUTTON_CANCEL = "Cancel"

MAIN_MENU_BUTTONS = {
    MENU_SONGS,
    MENU_SEARCH,
    MENU_TAGS,
    MENU_HELP,
    MENU_ADD_SONG,
    MENU_UPLOAD_CHART,
    MENU_BACKUP,
}


def is_private_chat(update: Update) -> bool:
    chat = getattr(update, "effective_chat", None)
    chat_type = getattr(chat, "type", None)
    return isinstance(chat_type, str) and chat_type == "private"


def is_admin_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    settings = get_settings(context)
    return user.id in settings.admin_telegram_user_ids


def home_menu_markup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> ReplyKeyboardMarkup | None:
    if not is_private_chat(update):
        return None

    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(MENU_SONGS), KeyboardButton(MENU_SEARCH)],
        [KeyboardButton(MENU_TAGS), KeyboardButton(MENU_HELP)],
    ]
    if is_admin_user(update, context):
        rows.extend(
            [
                [KeyboardButton(MENU_ADD_SONG), KeyboardButton(MENU_UPLOAD_CHART)],
                [KeyboardButton(MENU_BACKUP)],
            ]
        )
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def button_row_markup(
    update: Update,
    rows: Sequence[Sequence[str]],
) -> ReplyKeyboardMarkup | None:
    if not is_private_chat(update):
        return None
    keyboard = [[KeyboardButton(value) for value in row] for row in rows]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def cancel_markup(update: Update) -> ReplyKeyboardMarkup | None:
    return button_row_markup(update, [[BUTTON_CANCEL]])


def skip_cancel_markup(update: Update) -> ReplyKeyboardMarkup | None:
    return button_row_markup(update, [[BUTTON_SKIP, BUTTON_CANCEL]])
