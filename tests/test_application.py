from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import MenuButtonCommands

from bot.application import post_init


@pytest.mark.asyncio
async def test_post_init_publishes_start_command_and_commands_menu_button() -> None:
    application = SimpleNamespace(
        bot_data={},
        bot=SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_chat_menu_button=AsyncMock(),
        ),
    )

    await post_init(application)

    application.bot.set_my_commands.assert_awaited_once()
    commands = application.bot.set_my_commands.await_args.args[0]
    assert len(commands) == 1
    assert commands[0].command == "start"
    assert commands[0].description == "Відкрити головне меню"

    application.bot.set_chat_menu_button.assert_awaited_once()
    menu_button = application.bot.set_chat_menu_button.await_args.kwargs["menu_button"]
    assert isinstance(menu_button, MenuButtonCommands)
