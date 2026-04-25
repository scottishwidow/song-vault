import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram import BotCommand, MenuButtonCommands, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.runtime import (
    BACKUP_SERVICE_KEY,
    CHART_SERVICE_KEY,
    ENGINE_KEY,
    SETTINGS_KEY,
    SONG_SERVICE_KEY,
)
from config.settings import Settings
from handlers.backup import build_import_backup_handler
from handlers.charts import build_upload_chart_handler
from handlers.common import error_handler, start_command
from handlers.navigation import build_menu_text_handler, build_navigation_callback_handler
from handlers.repertoire import build_add_song_handler, build_edit_song_handler
from services.chart_service import ChartService
from services.repertoire_backup_service import RepertoireBackupService
from services.song_service import SongService
from storage.s3_chart_storage import S3ChartStorage

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    chart_service = application.bot_data.get(CHART_SERVICE_KEY)
    if isinstance(chart_service, ChartService):
        await chart_service.ensure_storage_ready()
    await application.bot.set_my_commands([BotCommand("start", "Відкрити головне меню")])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def post_shutdown(application: Application) -> None:
    engine = application.bot_data.get(ENGINE_KEY)
    if isinstance(engine, AsyncEngine):
        await engine.dispose()


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Невідома команда. Скористайтеся кнопками меню або надішліть /start."
        )


def build_application(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> Application:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    storage = S3ChartStorage.from_settings(settings)

    application.bot_data[SETTINGS_KEY] = settings
    application.bot_data[SONG_SERVICE_KEY] = SongService(session_factory)
    application.bot_data[CHART_SERVICE_KEY] = ChartService(
        session_factory=session_factory,
        storage=storage,
    )
    application.bot_data[BACKUP_SERVICE_KEY] = RepertoireBackupService(
        session_factory=session_factory,
        storage=storage,
    )
    application.bot_data[ENGINE_KEY] = engine

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(build_add_song_handler())
    application.add_handler(build_edit_song_handler())
    application.add_handler(build_upload_chart_handler())
    application.add_handler(build_import_backup_handler())
    application.add_handler(build_navigation_callback_handler())
    application.add_handler(build_menu_text_handler())
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler)

    logger.info("Application initialized")
    return application
