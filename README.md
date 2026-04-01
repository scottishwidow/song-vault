# Song Vault

Song Vault is a Python Telegram bot for repertoire management. It uses `python-telegram-bot`, `uv`, SQLAlchemy, Alembic, Postgres, and S3-compatible chart storage (MinIO in local development).

## What it includes

- Async Telegram bot skeleton with polling
- Admin-only repertoire CRUD flow
- Admin-only chart upload flow with one active chart per song
- Chart retrieval by song ID
- Postgres-backed persistence and Alembic migrations
- Ruff, mypy, pytest, pre-commit, and GitHub Actions

## Quick start

1. Copy environment configuration:

   ```bash
   cp .env.example .env
   ```

2. Set `TELEGRAM_BOT_TOKEN` in `.env`.

3. Start the full local stack (Postgres, MinIO, bucket init, and bot):

   ```bash
   docker compose up -d
   ```

4. Follow logs:

   ```bash
   docker compose logs -f bot
   ```

## Alternative local run (bot outside Compose)

1. Install dependencies:

   ```bash
   uv sync --dev
   ```

2. Start infrastructure only:

   ```bash
   docker compose up -d db minio minio-init
   ```

3. Run migrations and start bot:

   ```bash
   uv run alembic upgrade head
   uv run song-vault
   ```

## Common quality commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
TEST_DATABASE_URL=postgresql+asyncpg://song_vault:song_vault@localhost:5432/song_vault uv run pytest tests/test_postgres_integration.py
uv run pre-commit run --all-files
```

## Environment variables

- `TELEGRAM_BOT_TOKEN`: bot token from BotFather
- `ADMIN_TELEGRAM_USER_IDS`: comma-separated Telegram user IDs allowed to modify repertoire
- `DATABASE_URL`: SQLAlchemy async database URL
- `TEST_DATABASE_URL`: optional SQLAlchemy async Postgres URL used for migration/persistence integration tests
- `LOG_LEVEL`: application logging level
- `BOT_POLL_INTERVAL`: long-polling interval in seconds
- `CHART_STORAGE_ENDPOINT_URL`: S3-compatible endpoint URL
- `CHART_STORAGE_REGION`: object storage region (default: `us-east-1`)
- `CHART_STORAGE_BUCKET`: chart bucket name
- `CHART_STORAGE_ACCESS_KEY_ID`: object storage access key
- `CHART_STORAGE_SECRET_ACCESS_KEY`: object storage secret key
- `CHART_STORAGE_USE_SSL`: use HTTPS for storage (`true`/`false`)
- `CHART_STORAGE_FORCE_PATH_STYLE`: force S3 path-style addressing (`true`/`false`)
