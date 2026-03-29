# Song Vault

Song Vault is a Python Telegram bot for repertoire management. The baseline in this repository uses `python-telegram-bot`, `uv`, SQLAlchemy, Alembic, and Postgres.

## What it includes

- Async Telegram bot skeleton with polling
- Admin-only repertoire CRUD flow
- Postgres-backed persistence and Alembic migrations
- Ruff, mypy, pytest, pre-commit, and GitHub Actions

## Quick start

1. Install dependencies:

   ```bash
   uv sync --dev
   ```

2. Start Postgres:

   ```bash
   docker compose up -d db
   ```

3. Copy environment configuration:

   ```bash
   cp .env.example .env
   ```

4. Run migrations:

   ```bash
   uv run alembic upgrade head
   ```

5. Start the bot:

   ```bash
   uv run song-vault
   ```

## Common commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pre-commit run --all-files
```

## Environment variables

- `TELEGRAM_BOT_TOKEN`: bot token from BotFather
- `ADMIN_TELEGRAM_USER_IDS`: comma-separated Telegram user IDs allowed to modify repertoire
- `DATABASE_URL`: SQLAlchemy async database URL
- `LOG_LEVEL`: application logging level
- `BOT_POLL_INTERVAL`: long-polling interval in seconds
