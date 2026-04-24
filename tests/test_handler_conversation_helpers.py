from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import Chat, Message, ReplyKeyboardRemove, Update, User
from telegram.ext import MessageHandler

from bot.runtime import SETTINGS_KEY
from config.settings import Settings
from handlers.conversation import (
    cancel_message_fallback,
    conversation_message_filter,
    home_or_remove_markup,
    parse_callback_int,
    parse_callback_int_pair,
    parse_song_id_arg,
)
from handlers.ui import BUTTON_CANCEL


def build_context(*, admin_ids: tuple[int, ...] = (1,)) -> SimpleNamespace:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=admin_ids,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={SETTINGS_KEY: settings}),
    )


def build_update(*, text: str = "value", chat_type: str = "private") -> Update:
    user = User(id=1, first_name="Test", is_bot=False)
    chat = Chat(id=1, type=chat_type)
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=1, message=message)


def test_parse_song_id_arg_accepts_exactly_one_numeric_arg() -> None:
    assert parse_song_id_arg(["42"]) == 42


def test_parse_song_id_arg_rejects_missing_extra_and_non_numeric_args() -> None:
    assert parse_song_id_arg([]) is None
    assert parse_song_id_arg(["42", "43"]) is None
    assert parse_song_id_arg(["abc"]) is None


def test_parse_callback_int_accepts_prefixed_numeric_payload() -> None:
    assert parse_callback_int("edit:start:42", prefix="edit:start:") == 42


def test_parse_callback_int_rejects_malformed_or_non_string_payload() -> None:
    assert parse_callback_int(None, prefix="edit:start:") is None
    assert parse_callback_int(42, prefix="edit:start:") is None
    assert parse_callback_int("upload:start:42", prefix="edit:start:") is None
    assert parse_callback_int("edit:start:abc", prefix="edit:start:") is None
    assert parse_callback_int("edit:start:42:0", prefix="edit:start:") is None


def test_parse_callback_int_pair_accepts_prefixed_song_id_and_page_payload() -> None:
    assert parse_callback_int_pair("song:detail:42:3", prefix="song:detail:") == (42, 3)


def test_parse_callback_int_pair_rejects_malformed_payload() -> None:
    assert parse_callback_int_pair(None, prefix="song:detail:") is None
    assert parse_callback_int_pair(42, prefix="song:detail:") is None
    assert parse_callback_int_pair("song:view:42:3", prefix="song:detail:") is None
    assert parse_callback_int_pair("song:detail:42", prefix="song:detail:") is None
    assert parse_callback_int_pair("song:detail:42:3:9", prefix="song:detail:") is None
    assert parse_callback_int_pair("song:detail:abc:3", prefix="song:detail:") is None
    assert parse_callback_int_pair("song:detail:42:abc", prefix="song:detail:") is None


def test_cancel_fallback_filter_wins_over_conversation_state_filter() -> None:
    update = build_update(text=BUTTON_CANCEL)
    state_handler = MessageHandler(conversation_message_filter(), AsyncMock())
    fallback = cancel_message_fallback(AsyncMock())

    assert not bool(state_handler.check_update(update))
    assert bool(fallback.check_update(update))


def test_home_or_remove_markup_removes_keyboard_outside_private_chats() -> None:
    update = build_update(chat_type="group")
    context = build_context()

    assert isinstance(home_or_remove_markup(update, context), ReplyKeyboardRemove)
