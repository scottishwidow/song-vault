# Repository Guidelines

## Purpose

This repository hosts a Telegram bot for repertoire management. Keep the baseline simple, async-first, and service-oriented.

## Commit Hygiene
- After completing any task, **always propose a commit message** if the task is code based.
- If the current branch is `main`, **always create and switch to a new branch** before making code changes.
- The commit message must follow a consistent structure:
  - Short, descriptive title (imperative mood)
  - Optional body with context if needed

**Example:**

`feat(ci): introduce pre-commit hooks`


## Preferred workflow

- Use `uv` for dependency management and command execution.
- Use Docker Compose when running the local stack (database, object storage, bot).
- Keep Telegram handlers thin. Business logic belongs in `services/`.
- Treat Postgres as the primary database. Test-only SQLite usage is acceptable when it does not leak into runtime code.
- Prefer explicit typing and pass `ruff`, `mypy`, and `pytest` before finalizing changes.

## Architecture boundaries

- `handlers/` owns Telegram update parsing and response formatting.
- `services/` owns repertoire operations and validation.
- `models/` owns SQLAlchemy mappings and enum definitions.
- `db/` owns engine, sessions, and metadata wiring.
- `config/` owns environment-driven settings only.

## Commands

```bash
uv sync --dev
uv run alembic upgrade head
uv run song-vault
docker compose up -d --build
docker compose logs -f bot
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
```

## Editing expectations

- Preserve async boundaries end-to-end.
- Add tests for service-layer and handler-layer changes.
- Use soft archive semantics instead of hard deletes unless the task explicitly requires otherwise.
- Keep documentation current when commands, env vars, or architecture change.
- After finishing a feature or a fix for an existing feature, add or update a matching implementation note in `docs/features/`.
