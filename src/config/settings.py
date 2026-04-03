from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    admin_telegram_user_ids: tuple[int, ...] = Field(
        default_factory=tuple,
        alias="ADMIN_TELEGRAM_USER_IDS",
    )
    database_url: str = Field(alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    bot_poll_interval: float = Field(default=1.0, alias="BOT_POLL_INTERVAL")
    chart_storage_endpoint_url: str = Field(
        default="http://localhost:9000",
        alias="CHART_STORAGE_ENDPOINT_URL",
    )
    chart_storage_region: str = Field(default="us-east-1", alias="CHART_STORAGE_REGION")
    chart_storage_bucket: str = Field(
        default="song-vault-charts",
        alias="CHART_STORAGE_BUCKET",
    )
    chart_storage_access_key_id: SecretStr = Field(
        default_factory=lambda: SecretStr("songvault"),
        alias="CHART_STORAGE_ACCESS_KEY_ID",
    )
    chart_storage_secret_access_key: SecretStr = Field(
        default_factory=lambda: SecretStr("songvaultsecret"),
        alias="CHART_STORAGE_SECRET_ACCESS_KEY",
    )
    chart_storage_use_ssl: bool = Field(default=False, alias="CHART_STORAGE_USE_SSL")
    chart_storage_force_path_style: bool = Field(
        default=True,
        alias="CHART_STORAGE_FORCE_PATH_STYLE",
    )

    @field_validator("admin_telegram_user_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, int):
            return (value,)
        if isinstance(value, str):
            return tuple(int(part.strip()) for part in value.split(",") if part.strip())
        if isinstance(value, list | tuple | set):
            return tuple(int(part) for part in value)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
