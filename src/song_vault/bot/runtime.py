from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine
from telegram.ext import ContextTypes

from song_vault.config.settings import Settings
from song_vault.services.chart_service import ChartService
from song_vault.services.song_service import SongService

ENGINE_KEY = "engine"
SETTINGS_KEY = "settings"
SONG_SERVICE_KEY = "song_service"
CHART_SERVICE_KEY = "chart_service"


def get_settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return cast(Settings, context.application.bot_data[SETTINGS_KEY])


def get_song_service(context: ContextTypes.DEFAULT_TYPE) -> SongService:
    return cast(SongService, context.application.bot_data[SONG_SERVICE_KEY])


def get_chart_service(context: ContextTypes.DEFAULT_TYPE) -> ChartService:
    return cast(ChartService, context.application.bot_data[CHART_SERVICE_KEY])


def get_engine(context: ContextTypes.DEFAULT_TYPE) -> AsyncEngine:
    return cast(AsyncEngine, context.application.bot_data[ENGINE_KEY])
