from song_vault.config.settings import Settings


def test_admin_telegram_user_ids_accepts_single_int() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=1,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )

    assert settings.admin_telegram_user_ids == (1,)


def test_admin_telegram_user_ids_accepts_csv_string() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS="1, 2,3",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )

    assert settings.admin_telegram_user_ids == (1, 2, 3)
