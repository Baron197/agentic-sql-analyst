"""Settings loaded from environment variables and `.env`."""

from functools import lru_cache

from psycopg.conninfo import make_conninfo
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Secrets have no default and must come from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "arunika"
    postgres_user: str = "postgres"
    postgres_password: SecretStr = SecretStr("")

    def admin_conninfo(self) -> str:
        """Connection string for the owner role (schema setup and seeding only, never the agent)."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            dbname=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
