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


def test_chart_storage_defaults_are_set() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )

    assert settings.chart_storage_endpoint_url == "http://localhost:9000"
    assert settings.chart_storage_region == "us-east-1"
    assert settings.chart_storage_bucket == "song-vault-charts"
    assert settings.chart_storage_access_key_id.get_secret_value() == "songvault"
    assert settings.chart_storage_secret_access_key.get_secret_value() == "songvaultsecret"
    assert settings.chart_storage_use_ssl is False
    assert settings.chart_storage_force_path_style is True


def test_chart_storage_settings_parse_overrides() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        CHART_STORAGE_ENDPOINT_URL="https://object-store.example.com",
        CHART_STORAGE_REGION="eu-west-1",
        CHART_STORAGE_BUCKET="charts-prod",
        CHART_STORAGE_ACCESS_KEY_ID="abc",
        CHART_STORAGE_SECRET_ACCESS_KEY="def",
        CHART_STORAGE_USE_SSL=True,
        CHART_STORAGE_FORCE_PATH_STYLE=False,
    )

    assert settings.chart_storage_endpoint_url == "https://object-store.example.com"
    assert settings.chart_storage_region == "eu-west-1"
    assert settings.chart_storage_bucket == "charts-prod"
    assert settings.chart_storage_access_key_id.get_secret_value() == "abc"
    assert settings.chart_storage_secret_access_key.get_secret_value() == "def"
    assert settings.chart_storage_use_ssl is True
    assert settings.chart_storage_force_path_style is False
