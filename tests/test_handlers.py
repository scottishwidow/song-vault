from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from song_vault.bot.runtime import CHART_SERVICE_KEY, SETTINGS_KEY
from song_vault.config.settings import Settings
from song_vault.handlers.charts import chart_command, upload_chart_start
from song_vault.handlers.common import ensure_admin
from song_vault.handlers.repertoire import search_songs_command
from song_vault.services.chart_service import SongChartNotFoundError
from song_vault.services.song_service import SongNotFoundError


def build_context(
    *,
    args: list[str] | None = None,
    admin_ids: tuple[int, ...] = (1,),
    chart_service: object | None = None,
) -> SimpleNamespace:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=admin_ids,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return SimpleNamespace(
        args=args or [],
        user_data={},
        application=SimpleNamespace(
            bot_data={
                SETTINGS_KEY: settings,
                CHART_SERVICE_KEY: chart_service,
            }
        ),
    )


def build_update(*, user_id: int = 1) -> tuple[SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply, text=None)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
    )
    return update, reply


@pytest.mark.asyncio
async def test_ensure_admin_rejects_non_admin() -> None:
    update, reply = build_update(user_id=999)
    context = build_context(admin_ids=(1,))

    allowed = await ensure_admin(update, context)

    assert allowed is False
    reply.assert_awaited_once_with("Admin access is required for this command.")


@pytest.mark.asyncio
async def test_search_command_requires_query() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await search_songs_command(update, context)

    reply.assert_awaited_once_with("Usage: /search <text>")


@pytest.mark.asyncio
async def test_chart_command_requires_song_id() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await chart_command(update, context)

    reply.assert_awaited_once_with("Usage: /chart <song_id>")


@pytest.mark.asyncio
async def test_chart_command_reports_missing_chart() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        get_active_chart_file=AsyncMock(side_effect=SongChartNotFoundError())
    )
    context = build_context(args=["7"], chart_service=chart_service)

    await chart_command(update, context)

    reply.assert_awaited_once_with("No chart uploaded yet for song #7.")


@pytest.mark.asyncio
async def test_upload_chart_start_requires_admin() -> None:
    update, reply = build_update(user_id=2)
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=["5"], admin_ids=(1,), chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Admin access is required for this command.")
    chart_service.assert_song_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_chart_start_requires_song_id_arg() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=[], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Usage: /uploadchart <song_id>")


@pytest.mark.asyncio
async def test_upload_chart_start_reports_missing_song() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        assert_song_exists=AsyncMock(side_effect=SongNotFoundError("Song 10 was not found."))
    )
    context = build_context(args=["10"], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Song 10 was not found.")
