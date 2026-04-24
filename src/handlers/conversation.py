from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from typing import Any, cast

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import BaseHandler, ContextTypes, MessageHandler, filters

from handlers.ui import CANCEL_BUTTON_PATTERN, home_menu_markup


def user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)


def parse_song_id_arg(args: Sequence[str]) -> int | None:
    if len(args) != 1:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


def parse_callback_int(data: object, *, prefix: str) -> int | None:
    if not isinstance(data, str) or not data.startswith(prefix):
        return None
    raw_value = data[len(prefix) :]
    try:
        return int(raw_value)
    except ValueError:
        return None


def parse_callback_int_pair(data: object, *, prefix: str) -> tuple[int, int] | None:
    if not isinstance(data, str) or not data.startswith(prefix):
        return None
    parts = data[len(prefix) :].split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def cancel_message_filter() -> filters.BaseFilter:
    return filters.Regex(CANCEL_BUTTON_PATTERN) & ~filters.COMMAND & filters.UpdateType.MESSAGE


def conversation_message_filter(
    base_filter: filters.BaseFilter = filters.TEXT,
) -> filters.BaseFilter:
    return (
        base_filter
        & ~filters.COMMAND
        & ~filters.Regex(CANCEL_BUTTON_PATTERN)
        & filters.UpdateType.MESSAGE
    )


def cancel_message_fallback(
    callback: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, object]],
) -> BaseHandler:
    return MessageHandler(cancel_message_filter(), callback)


def home_or_remove_markup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    return home_menu_markup(update, context) or ReplyKeyboardRemove()


async def reply_state_lost(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            message,
            reply_markup=home_or_remove_markup(update, context),
        )
