# Song Vault

Song Vault is a Python Telegram bot for repertoire management. It uses `python-telegram-bot`, `uv`, SQLAlchemy, Alembic, Postgres, and S3-compatible chart storage (MinIO in local development).

The MVP is complete. The current repository baseline is the finished admin-operated repertoire bot plus documentation for follow-on feature planning in `docs/features/`.

## What it includes

- Async Telegram bot skeleton with polling
- Button-first Telegram navigation (reply keyboard + inline actions)
- Admin-only repertoire CRUD flow
- Rich song metadata fields: capo, time signature, and arrangement notes
- Admin-only chart upload flow with one active chart per song
- Chart retrieval by song ID
- Admin-only repertoire backup export/import (ZIP with chart binaries)
- `/start` as the only typed entry/reset path; all other user actions stay in buttons
- Postgres-backed persistence and Alembic migrations
- Ruff, mypy, pytest, pre-commit, and GitHub Actions

## Documentation

- [Architecture](docs/architecture.md)
- [MVP scope](docs/mvp.md)
- [Feature implementation plans](docs/features/README.md)

## Quick start

1. Copy environment configuration:

   ```bash
   cp .env.example .env
   ```

2. Set `TELEGRAM_BOT_TOKEN` in `.env`.

3. Build and start the full local stack (Postgres, MinIO, bucket init, and bot):

   ```bash
   docker compose up -d --build
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

## Docker Hub publish pipeline

The repository includes a GitHub Actions workflow at `.github/workflows/docker-publish.yml` that builds and pushes the app image to Docker Hub on:

- pushes of Git tags matching `v*`

The published Docker tag is the same as the Git tag that triggered the workflow (for example, pushing `v1.2.3` publishes the Docker tag `v1.2.3`).

Set these GitHub Actions secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (Docker Hub access token)

Optional repository variable:

- `DOCKERHUB_IMAGE` (defaults to `<DOCKERHUB_USERNAME>/song-vault`)

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
