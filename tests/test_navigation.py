from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.runtime import CHART_SERVICE_KEY, SETTINGS_KEY, SONG_SERVICE_KEY
from config.settings import Settings
from handlers.navigation import (
    SEARCH_PENDING_KEY,
    SONG_BROWSER_STATE_KEY,
    build_navigation_callback_handler,
    menu_text_router,
)
from handlers.navigation import (
    navigation_callback_router as navigation_callback_router,
)
from handlers.ui import MENU_BACKUP, MENU_SEARCH, MENU_SONGS, MENU_START, MENU_UPLOAD_CHART
from models.song import Song, SongStatus
from services.chart_service import ChartFile


def build_song(
    *,
    song_id: int = 5,
    title: str = "Amazing Grace",
    artist: str = "Traditional",
    source_url: str | None = None,
) -> Song:
    song = Song(
        title=title,
        artist=artist,
        source_url=source_url,
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
    chart_service: object | None = None,
    admin_ids: tuple[int, ...] = (1,),
) -> SimpleNamespace:
    if chart_service is None:
        chart_service = SimpleNamespace(has_active_chart=AsyncMock(return_value=True))
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
                CHART_SERVICE_KEY: chart_service,
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
    reply_document = AsyncMock()
    reply_photo = AsyncMock()
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(
            reply_text=reply,
            reply_document=reply_document,
            reply_photo=reply_photo,
        ),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_message=SimpleNamespace(
            reply_text=reply,
            reply_document=reply_document,
            reply_photo=reply_photo,
        ),
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type="private"),
    )
    return update, query


def assert_link_previews_disabled(call: object) -> None:
    assert call.kwargs["link_preview_options"].is_disabled is True


@pytest.mark.asyncio
async def test_menu_songs_button_opens_song_browser() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[build_song()]))
    context = build_context(song_service=song_service)
    update, reply = build_message_update(text=MENU_SONGS)

    await menu_text_router(update, context)

    assert SONG_BROWSER_STATE_KEY in context.user_data
    reply.assert_awaited_once()
    message_text = reply.await_args.args[0]
    assert "Активні пісні (1)" in message_text
    keyboard = reply.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "song:detail:5:0"


@pytest.mark.asyncio
async def test_plain_songs_label_opens_song_browser() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[build_song()]))
    context = build_context(song_service=song_service)
    update, reply = build_message_update(text="Пісні")

    await menu_text_router(update, context)

    assert SONG_BROWSER_STATE_KEY in context.user_data
    reply.assert_awaited_once()
    message_text = reply.await_args.args[0]
    assert "Активні пісні (1)" in message_text
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
    assert prompt_reply.await_args.args[0] == (
        "Надішліть запит для пошуку або натисніть «Скасувати»."
    )
    query_update, query_reply = build_message_update(text="grace")
    query_update.effective_user = prompt_update.effective_user
    query_update.effective_chat = prompt_update.effective_chat

    await menu_text_router(query_update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    query_reply.assert_awaited_once()
    message_text = query_reply.await_args.args[0]
    assert 'Результати для "grace" (1)' in message_text


@pytest.mark.asyncio
async def test_start_button_returns_home_screen_and_clears_navigation_state() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    context.user_data[SEARCH_PENDING_KEY] = True
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [],
        "current_page": 0,
    }
    update, reply = build_message_update(text=MENU_START)

    await menu_text_router(update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    assert SONG_BROWSER_STATE_KEY not in context.user_data
    reply.assert_awaited_once()
    assert reply.await_args.args[0] == "Бот готовий.\nКористуйтеся кнопками меню нижче."
    keyboard = reply.await_args.kwargs["reply_markup"]
    rows = [[button.text for button in row] for row in keyboard.keyboard]
    assert rows[0] == [MENU_START, MENU_SONGS]


@pytest.mark.asyncio
async def test_search_cancel_returns_home_screen() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    prompt_update, _ = build_message_update(text=MENU_SEARCH)

    await menu_text_router(prompt_update, context)

    cancel_update, cancel_reply = build_message_update(text="Скасувати")
    cancel_update.effective_user = prompt_update.effective_user
    cancel_update.effective_chat = prompt_update.effective_chat

    await menu_text_router(cancel_update, context)

    assert SEARCH_PENDING_KEY not in context.user_data
    cancel_reply.assert_awaited_once()
    assert cancel_reply.await_args.args[0] == (
        "Скасовано.\nБот готовий.\nКористуйтеся кнопками меню нижче."
    )
    keyboard = cancel_reply.await_args.kwargs["reply_markup"]
    assert keyboard.keyboard[0][0].text == MENU_START


@pytest.mark.asyncio
async def test_menu_search_empty_results_uses_specific_copy() -> None:
    song_service = SimpleNamespace(
        search_songs=AsyncMock(return_value=[]),
        list_songs=AsyncMock(return_value=[]),
    )
    context = build_context(song_service=song_service)
    prompt_update, _ = build_message_update(text=MENU_SEARCH)
    await menu_text_router(prompt_update, context)

    query_update, query_reply = build_message_update(text="missing")
    query_update.effective_user = prompt_update.effective_user
    query_update.effective_chat = prompt_update.effective_chat

    await menu_text_router(query_update, context)

    query_reply.assert_awaited_once_with("За цим запитом пісень не знайдено.")


@pytest.mark.asyncio
async def test_menu_tags_empty_state_uses_specific_copy() -> None:
    song_service = SimpleNamespace(list_tags=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    update, reply = build_message_update(text="Теги")

    await menu_text_router(update, context)

    reply.assert_awaited_once_with("Теги ще не додано.")


@pytest.mark.asyncio
async def test_upload_menu_rejects_non_admin_with_shared_copy() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock())
    context = build_context(song_service=song_service, admin_ids=(1,))
    update, reply = build_message_update(text=MENU_UPLOAD_CHART, user_id=2)

    await menu_text_router(update, context)

    reply.assert_awaited_once_with("Ця дія доступна лише адміністраторам.")
    song_service.list_songs.assert_not_awaited()


@pytest.mark.asyncio
async def test_backup_menu_rejects_non_admin_with_shared_copy() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock())
    context = build_context(song_service=song_service, admin_ids=(1,))
    update, reply = build_message_update(text=MENU_BACKUP, user_id=2)

    await menu_text_router(update, context)

    reply.assert_awaited_once_with("Ця дія доступна лише адміністраторам.")


@pytest.mark.asyncio
async def test_song_detail_for_non_admin_hides_admin_action_buttons() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    chart_service = SimpleNamespace(has_active_chart=AsyncMock(return_value=True))
    context = build_context(song_service=song_service, chart_service=chart_service, admin_ids=(1,))
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [{"id": 5, "title": "Amazing Grace", "artist": "Traditional"}],
        "current_page": 0,
    }
    update, query = build_callback_update(data="song:detail:5:0", user_id=2)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Редагувати" not in labels
    assert "Архівувати" not in labels
    assert "Завантажити гармонію" not in labels
    assert "Переглянути гармонію" in labels
    assert "Назад до результатів" in labels
    chart_service.has_active_chart.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_song_detail_for_non_admin_hides_chart_button_when_no_active_chart() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    chart_service = SimpleNamespace(has_active_chart=AsyncMock(return_value=False))
    context = build_context(song_service=song_service, chart_service=chart_service, admin_ids=(1,))
    update, query = build_callback_update(data="song:detail:5:0", user_id=2)

    await navigation_callback_router(update, context)

    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Переглянути гармонію" not in labels
    assert "Редагувати" not in labels
    assert "Архівувати" not in labels
    assert "Завантажити гармонію" not in labels
    assert "Назад до результатів" in labels
    chart_service.has_active_chart.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_song_detail_for_admin_shows_admin_action_buttons() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    chart_service = SimpleNamespace(has_active_chart=AsyncMock(return_value=True))
    context = build_context(song_service=song_service, chart_service=chart_service, admin_ids=(1,))
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [{"id": 5, "title": "Amazing Grace", "artist": "Traditional"}],
        "current_page": 0,
    }
    update, query = build_callback_update(data="song:detail:5:0", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Редагувати" in labels
    assert "Архівувати" in labels
    assert "Завантажити гармонію" in labels
    assert "Переглянути гармонію" in labels
    chart_service.has_active_chart.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_song_detail_for_admin_keeps_admin_actions_when_no_active_chart() -> None:
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    chart_service = SimpleNamespace(has_active_chart=AsyncMock(return_value=False))
    context = build_context(song_service=song_service, chart_service=chart_service, admin_ids=(1,))
    update, query = build_callback_update(data="song:detail:5:0", user_id=1)

    await navigation_callback_router(update, context)

    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Переглянути гармонію" not in labels
    assert "Редагувати" in labels
    assert "Архівувати" in labels
    assert "Завантажити гармонію" in labels
    chart_service.has_active_chart.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_song_detail_suppresses_previews_for_visible_source_url() -> None:
    song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service, admin_ids=(1,))
    update, query = build_callback_update(data="song:detail:5:0", user_id=1)

    await navigation_callback_router(update, context)

    query.edit_message_text.assert_awaited_once()
    assert (
        "Джерело (оригінал): https://example.org/source"
        in query.edit_message_text.await_args.args[0]
    )
    assert_link_previews_disabled(query.edit_message_text.await_args)


@pytest.mark.asyncio
async def test_manual_chart_callback_sends_image_chart_as_photo_with_caption() -> None:
    chart_file = ChartFile(
        song_id=5,
        song_title="Amazing Grace",
        original_filename="amazing-grace.png",
        content_type="image/png",
        source_url="https://example.org/chart",
        chart_key="G",
        content=b"chart-bytes",
    )
    song_service = SimpleNamespace()
    chart_service = SimpleNamespace(get_active_chart_file=AsyncMock(return_value=chart_file))
    context = build_context(song_service=song_service, chart_service=chart_service)
    update, query = build_callback_update(data="song:view:5", user_id=2)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    chart_service.get_active_chart_file.assert_awaited_once_with(5)
    update.effective_message.reply_photo.assert_awaited_once()
    kwargs = update.effective_message.reply_photo.await_args.kwargs
    assert kwargs["caption"] == (
        "Пісня #5: Amazing Grace\n"
        "Тональність гармонії: G\n"
        "Джерело гармонії: https://example.org/chart"
    )
    assert kwargs["photo"].filename == "amazing-grace.png"
    update.effective_message.reply_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_browse_page_callback_recovers_state_and_renders_page() -> None:
    song = build_song()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)
    update, query = build_callback_update(data="browser:page:b:0", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    song_service.list_songs.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    rendered = query.edit_message_text.await_args.args[0]
    assert "Активні пісні (1)" in rendered
    assert context.user_data[SONG_BROWSER_STATE_KEY]["mode"] == "browse"
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "song:detail:5:0"


@pytest.mark.asyncio
async def test_stale_upload_page_callback_recovers_state_and_renders_page() -> None:
    song = build_song()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)
    update, query = build_callback_update(data="browser:page:u:0", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    song_service.list_songs.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    rendered = query.edit_message_text.await_args.args[0]
    assert "Оберіть пісню для завантаження гармонії (1)" in rendered
    assert context.user_data[SONG_BROWSER_STATE_KEY]["mode"] == "upload"
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "upload:start:5"


def test_navigation_callback_handler_matches_song_and_browser_callbacks() -> None:
    handler = build_navigation_callback_handler()

    assert handler.pattern.match("song:detail:5:0")
    assert handler.pattern.match("song:view:5")
    assert handler.pattern.match("song:archive:5:0")
    assert handler.pattern.match("song:archiveconfirm:5:0")
    assert handler.pattern.match("browser:page:b:0")
    assert handler.pattern.match("browser:close")
    assert handler.pattern.match("backup:menu")
    assert handler.pattern.match("backup:export")
    assert handler.pattern.match("backup:close")
    assert handler.pattern.match("nav:home")
    assert not handler.pattern.match("backup:import:start")


@pytest.mark.asyncio
async def test_archive_confirmation_success_sends_next_actions() -> None:
    archived_song = build_song()
    song_service = SimpleNamespace(archive_song=AsyncMock(return_value=archived_song))
    context = build_context(song_service=song_service, admin_ids=(1,))
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [{"id": 5, "title": "Amazing Grace", "artist": "Traditional"}],
        "current_page": 2,
    }
    update, query = build_callback_update(data="song:archiveconfirm:5:2", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    song_service.archive_song.assert_awaited_once_with(5)
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert update.effective_message.reply_text.await_count == 2
    success_call = update.effective_message.reply_text.await_args_list[0]
    assert success_call.args[0] == "Пісню #5 «Amazing Grace» архівовано."
    assert success_call.kwargs["reply_markup"].keyboard[0][0].text == MENU_START
    actions_call = update.effective_message.reply_text.await_args_list[1]
    callbacks = [
        button.callback_data
        for row in actions_call.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["song:detail:5:2", "browser:page:b:2", "nav:home"]


@pytest.mark.asyncio
async def test_archive_confirmation_rejects_non_admin_with_shared_copy() -> None:
    song_service = SimpleNamespace(archive_song=AsyncMock())
    context = build_context(song_service=song_service, admin_ids=(1,))
    update, query = build_callback_update(data="song:archiveconfirm:5:0", user_id=2)

    await navigation_callback_router(update, context)

    assert query.answer.await_count == 2
    query.answer.assert_any_await("Ця дія доступна лише адміністраторам.", show_alert=True)
    song_service.archive_song.assert_not_awaited()


@pytest.mark.asyncio
async def test_nav_home_callback_returns_home_screen() -> None:
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)
    context.user_data[SEARCH_PENDING_KEY] = True
    context.user_data[SONG_BROWSER_STATE_KEY] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [],
        "current_page": 0,
    }
    update, query = build_callback_update(data="nav:home", user_id=1)

    await navigation_callback_router(update, context)

    query.answer.assert_awaited_once()
    assert SEARCH_PENDING_KEY not in context.user_data
    assert SONG_BROWSER_STATE_KEY not in context.user_data
    update.effective_message.reply_text.assert_awaited_once()
    assert update.effective_message.reply_text.await_args.args[0] == (
        "Бот готовий.\nКористуйтеся кнопками меню нижче."
    )
