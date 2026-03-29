import logging

from telegram import Update

from song_vault.bot.application import build_application
from song_vault.config.settings import get_settings
from song_vault.db.session import build_session_factory, create_engine


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    application = build_application(
        settings=settings,
        session_factory=session_factory,
        engine=engine,
    )
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        poll_interval=settings.bot_poll_interval,
    )
