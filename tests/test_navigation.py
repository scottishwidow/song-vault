from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.runtime import SETTINGS_KEY, SONG_SERVICE_KEY
from config.settings import Settings
from handlers.navigation import SEARCH_PENDING_KEY, SONG_BROWSER_STATE_KEY, menu_text_router
from handlers.navigation import navigation_callback_router as navigation_callback_router
from handlers.ui import MENU_SEARCH, MENU_SONGS, MENU_START
from models.song import Song, SongStatus


def build_song(
    *,
    song_id: int = 5,
    title: str = "Amazing Grace",
    artist_or_source: str = "Traditional",
) -> Song:
    song = Song(
        title=title,
        artist_or_source=artist_or_source,
        key="G",
        status=SongStatus.ACTIVE,
    )
    song.id = song_id
    now = datetime.now(UTC)
    song.created_at = now
    song.updated_at = now
    return song


def build_context(
    *,
    song_service: object,
    admin_ids: tuple[int, ...] = (1,),
) -> SimpleNamespace:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=admin_ids,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                SETTINGS_KEY: settings,
                SONG_SERVICE_KEY: song_service,
            }
        ),
    )


def build_message_update(*, text: str, user_id: int = 1) -> tuple[SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    message = SimpleNamespace(
        text=text,
        reply_text=reply,
    )
    chat = SimpleNamespace(type="private")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=chat,
        callback_query=None,
    )
    return update, reply


def build_callback_update(
    *,
    data: str,
    user_id: int = 1,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    reply = AsyncMock()
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=reply),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_message=SimpleNamespace(reply_text=reply),
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type="private"),
    )
    return update, query


@pytest.mark.asyncio
async def test_menu_songs_button_opens_song_browser() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[build_song()]))
    context = build_context(song_service=song_service)
    update, reply = build_message_update(text=MENU_SONGS)

    await menu_text_router(update, context)

    assert SONG_BROWSER_STATE_KEY in context.user_data
    reply.assert_awaited_once()
    message_text = reply.await_args.args[0]
    assert "Active songs (1)" in message_text
    keyboard = reply.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "song:detail:5:0"


@pytest.mark.asyncio
async def test_menu_search_prompt_then_query_opens_browser_results() -> None:
    song = build_song()
    song_service = SimpleNamespace(
        search_songs=AsyncMock(return_value=[song]),
        list_songs=AsyncMock(return_value=[]),
    )
    context = build_context(song_service=song_service)
    prompt_update, prompt_reply = build_message_update(text=MENU_SEARCH)

    await menu_text_router(prompt_update, context)

    assert context.user_data[SEARCH_PENDING_KEY] is True
    prompt_reply.assert_awaited_once()
    query_update, query_reply = build_message_update(text="grace")
    query_update.effective_user = prompt_update.effective_user
    query_update.effective_chat = prompt_update.effective_chat

    await menu_text_router(query_update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    query_reply.assert_awaited_once()
    message_text = query_reply.await_args.args[0]
    assert 'Matches for "grace" (1)' in message_text


@pytest.mark.asyncio
async def test_start_button_returns_home_screen_and_clears_navigation_state() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    context.user_data[SEARCH_PENDING_KEY] = True
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Active songs",
        "items": [],
    }
    update, reply = build_message_update(text=MENU_START)

    await menu_text_router(update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    assert SONG_BROWSER_STATE_KEY not in context.user_data
    reply.assert_awaited_once()
    assert reply.await_args.args[0] == "Song Vault is ready.\nUse the menu buttons below."
    keyboard = reply.await_args.kwargs["reply_markup"]
    rows = [[button.text for button in row] for row in keyboard.keyboard]
    assert rows[0] == [MENU_START, MENU_SONGS]


@pytest.mark.asyncio
async def test_search_cancel_returns_home_screen() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    prompt_update, _ = build_message_update(text=MENU_SEARCH)

    await menu_text_router(prompt_update, context)

    cancel_update, cancel_reply = build_message_update(text="Cancel")
    cancel_update.effective_user = prompt_update.effective_user
    cancel_update.effective_chat = prompt_update.effective_chat

    await menu_text_router(cancel_update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    cancel_reply.assert_awaited_once()
    assert cancel_reply.await_args.args[0] == (
        "Cancelled.\nSong Vault is ready.\nUse the menu buttons below."
    )
    keyboard = cancel_reply.await_args.kwargs["reply_markup"]
    assert keyboard.keyboard[0][0].text == MENU_START


@pytest.mark.asyncio
async def test_song_detail_for_non_admin_hides_admin_action_buttons() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service, admin_ids=(1,))
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Active songs",
        "items": [{"id": 5, "title": "Amazing Grace", "artist_or_source": "Traditional"}],
    }
    update, query = build_callback_update(data="song:detail:5:0", user_id=2)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Edit" not in labels
    assert "Archive" not in labels
    assert "Upload Chart" not in labels
    assert "View Chart" in labels
    assert "Back to Results" in labels


@pytest.mark.asyncio
async def test_song_detail_for_admin_shows_admin_action_buttons() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service, admin_ids=(1,))
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Active songs",
        "items": [{"id": 5, "title": "Amazing Grace", "artist_or_source": "Traditional"}],
    }
    update, query = build_callback_update(data="song:detail:5:0", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Edit" in labels
    assert "Archive" in labels
    assert "Upload Chart" in labels
