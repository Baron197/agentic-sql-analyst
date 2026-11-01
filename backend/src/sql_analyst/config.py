"""Settings loaded from environment variables and `.env`."""

from functools import lru_cache

from psycopg.conninfo import make_conninfo
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

READER_ROLE = "nlq_reader"
WRITER_ROLE = "app_writer"


class Settings(BaseSettings):
    """App settings. Secrets have no default and must come from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_host: str = "127.0.0.1"  # not "localhost": see docs/DECISIONS.md D006
    postgres_port: int = 5432
    postgres_db: str = "arunika"
    postgres_user: str = "postgres"
    postgres_password: SecretStr = SecretStr("")

    # Safety layer: the agent's read-only login and the key that signs its region scope.
    nlq_reader_password: SecretStr = SecretStr("")
    rls_signing_key: SecretStr = SecretStr("")  # hex, at least 32 bytes
    query_timeout_ms: int = 5_000
    query_row_limit: int = 1_000
    query_cost_limit: float = 250_000.0  # EXPLAIN total cost; calibration in docs/SECURITY.md

    # LLM: 'fake' is keyless (tests, CI); 'anthropic' or 'openai' are live and need their key
    # and Baron's OK to run.
    llm_provider: str = "fake"
    llm_model: str = "gpt-6-luna"  # the Phase 7 choice (D043)
    llm_effort: str = ""  # empty = the model's default effort
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # Agent (Phase 4): per-run budget guard, retrieval embeddings, and the run store.
    agent_max_llm_calls: int = 8
    agent_max_tokens: int = 60_000
    agent_max_cost_usd: float = 0.05
    agent_max_seconds: float = 60.0
    agent_max_repairs: int = 3
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: str = ".cache/fastembed"
    runs_dir: str = "runs"

    # API (Phase 5): sign-in, the run store's write-only login, and the spend controls.
    app_writer_password: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")  # at least 32 characters
    demo_analyst_password: SecretStr = SecretStr("")
    demo_manager_password: SecretStr = SecretStr("")
    session_hours: int = 8
    cookie_secure: bool = False  # True when served over HTTPS
    rate_limit_per_minute: int = 10  # questions per user
    daily_budget_usd: float = 1.0  # live spend per day (WIB), all users together
    live_mode_enabled: bool = False  # kill switch for paid model calls
    demo_login_enabled: bool = False  # one-click demo sign-in (public demo only)

    def admin_conninfo(self) -> str:
        """Connection string for the owner role (schema setup and seeding only, never the agent)."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            dbname=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
        )

    def reader_conninfo(self) -> str:
        """Connection string for the agent's read-only role."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            dbname=self.postgres_db,
            user=READER_ROLE,
            password=self.nlq_reader_password.get_secret_value(),
        )

    def writer_conninfo(self) -> str:
        """Connection string for the API's run store (schema app only; no analytics access)."""
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            dbname=self.postgres_db,
            user=WRITER_ROLE,
            password=self.app_writer_password.get_secret_value(),
        )

    def jwt_key(self) -> str:
        key = self.jwt_secret.get_secret_value()
        if len(key) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return key

    def signing_key(self) -> bytes:
        key = bytes.fromhex(self.rls_signing_key.get_secret_value())
        if len(key) < 32:
            raise ValueError("RLS_SIGNING_KEY must be at least 32 bytes of hex")
        return key


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
