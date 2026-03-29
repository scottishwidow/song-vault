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
