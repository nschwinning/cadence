"""Application settings loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration.

    Values are read from environment variables and an optional ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App metadata
    APP_NAME: str = "Cadence"
    APP_VERSION: str = "0.1.0"

    # Database (sync psycopg 3 driver)
    DATABASE_URL: str = "postgresql+psycopg://cadence:cadence@localhost:5435/cadence"

    # Dedicated database for the test suite. Kept separate from ``DATABASE_URL``
    # so tests never read or mutate development/production data. Provisioned and
    # schema-created on demand by the pytest fixtures.
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://cadence:cadence@localhost:5435/cadence_test"
    )

    # CORS origins, parsed from a comma-separated env value
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5174"]
    )

    # AI asset recommender. Keys are optional so the app boots without them;
    # a recommendation run fails cleanly when a required key is missing.
    OPENAI_API_KEY: str = ""
    SERP_API_KEY: str = ""
    RECOMMENDER_MODEL: str = "gpt-5-mini"
    # Opt-in offline stub for the recommender agent (no OpenAI/SerpAPI calls).
    # Intended for the Docker end-to-end smoke and local development; leave off
    # in production so the real agent runs and missing keys fail cleanly.
    RECOMMENDER_STUB: bool = False

    # Alpaca paper-trading credentials/config. Keys are optional so the app boots
    # without them; a rebalance run fails cleanly when a required key is missing.
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    # Use Alpaca's paper-trading endpoint (never live). Default True for safety.
    ALPACA_PAPER: bool = True
    # Opt-in offline stub for the Alpaca client (no network calls), for the
    # Docker end-to-end smoke or local dev without Alpaca credentials.
    ALPACA_STUB: bool = False

    # Model id the AI portfolio manager runs on.
    AI_PORTFOLIO_MODEL: str = "gpt-5-mini"

    # Shared secret guarding the daily-rebalance trigger. The cron sidecar sends
    # it in the ``X-Cron-Token`` header; the endpoint rejects any request whose
    # header does not match. Empty (the default) means no valid token exists, so
    # every trigger is rejected — the rebalance must be explicitly enabled by
    # configuring a non-empty token.
    REBALANCE_CRON_TOKEN: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS`` to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
