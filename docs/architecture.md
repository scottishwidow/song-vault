# Architecture

The application runs as a long-polling Telegram bot. Telegram updates enter through `python-telegram-bot` handlers, which delegate all repertoire operations to a service layer. Services persist data through SQLAlchemy async sessions backed by Postgres.

## Flow

1. `song_vault.app` loads settings, logging, and database engine configuration.
2. `song_vault.bot.application` builds the Telegram application and registers handlers.
3. Handlers authorize the caller, validate command input, and call `SongService`.
4. `SongService` reads or writes `Song` rows using SQLAlchemy.
5. Responses are formatted back into Telegram messages.

## Boundaries

- Handlers must not contain SQL queries.
- Services must not depend on Telegram update objects.
- Configuration is environment-driven and loaded once at startup.
- Alembic owns schema evolution from the first migration onward.
