from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from song_vault.bot.runtime import SETTINGS_KEY
from song_vault.config.settings import Settings
from song_vault.handlers.common import ensure_admin
from song_vault.handlers.repertoire import search_songs_command


def build_context(
    *,
    args: list[str] | None = None,
    admin_ids: tuple[int, ...] = (1,),
) -> SimpleNamespace:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=admin_ids,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return SimpleNamespace(
        args=args or [],
        application=SimpleNamespace(
            bot_data={
                SETTINGS_KEY: settings,
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
