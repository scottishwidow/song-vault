# Architecture

The application runs as a long-polling Telegram bot. Telegram updates enter through `python-telegram-bot` handlers, which delegate repertoire and chart operations to service-layer components. The UX is button-first via reply/inline keyboards, with slash commands kept as fallback. Song and chart metadata persist through SQLAlchemy async sessions backed by Postgres. Chart binaries live in S3-compatible object storage.

## Flow

1. `app` loads settings, logging, and database engine configuration.
2. `bot.application` builds the Telegram application and registers handlers.
3. On startup, `ChartService` verifies the chart storage bucket is reachable.
4. Handlers authorize the caller, route button/callback interactions, validate input, and call `SongService`, `ChartService`, or `RepertoireBackupService`.
5. Service-layer components read or write Postgres metadata rows.
6. `ChartService` and `RepertoireBackupService` store and retrieve chart binaries through the storage adapter.
7. Responses are formatted back into Telegram messages.

## Boundaries

- Handlers must not contain SQL queries.
- Services must not depend on Telegram update objects.
- Chart binaries must not be stored in Postgres.
- Configuration is environment-driven and loaded once at startup.
- Alembic owns schema evolution from the first migration onward.
