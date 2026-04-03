from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.application import post_init


@pytest.mark.asyncio
async def test_post_init_clears_published_bot_commands() -> None:
    application = SimpleNamespace(
        bot_data={},
        bot=SimpleNamespace(delete_my_commands=AsyncMock()),
    )

    await post_init(application)

    application.bot.delete_my_commands.assert_awaited_once_with()
