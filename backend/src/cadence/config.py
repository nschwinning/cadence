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
    # Web-search backend for the agents' ``web_search`` tool. ``serpapi`` uses the
    # SerpAPI SDK + ``SERP_API_KEY``; ``serper`` POSTs to serper.dev with
    # ``SERPER_API_KEY``. Defaults to ``serpapi`` so existing deployments are
    # unaffected; switching to Serper requires setting both this and SERPER_API_KEY.
    WEB_SEARCH_PROVIDER: str = "serpapi"
    SERP_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    RECOMMENDER_MODEL: str = "gpt-5-mini"
    # Opt-in offline stub for the recommender agent (no OpenAI/SerpAPI calls).
    # Intended for the Docker end-to-end smoke and local development; leave off
    # in production so the real agent runs and missing keys fail cleanly.
    RECOMMENDER_STUB: bool = False
    #: Wall-clock ceiling (seconds) for a single recommender agent run (search +
    #: reasoning). The agent verifies each candidate via web search, so a run that
    #: proposes many candidates needs headroom; raise this if runs time out.
    RECOMMENDER_AGENT_TIMEOUT_SECONDS: int = 300
    #: Hard SDK-enforced turn cap per recommender run (bounds tool-call loops).
    RECOMMENDER_MAX_TURNS: int = 24

    # Alpaca paper-trading credentials/config. Keys are optional so the app boots
    # without them; a rebalance run fails cleanly when a required key is missing.
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    # Use Alpaca's paper-trading endpoint (never live). Default True for safety.
    ALPACA_PAPER: bool = True
    # Opt-in offline stub for the Alpaca client (no network calls), for the
    # Docker end-to-end smoke or local dev without Alpaca credentials.
    ALPACA_STUB: bool = False

    # Annual risk-free rate used when computing a paper-trading session's Sharpe
    # ratio (as a decimal fraction, e.g. 0.04 for 4%). Defaults to 0, which is a
    # common simplification for a paper-trading dashboard; raise it to measure
    # excess return over a non-zero benchmark.
    SHARPE_RISK_FREE_RATE: float = 0.0

    # Fixed transaction cost charged on every executed paper trade (in USD, per
    # trade, regardless of side). Modeled so reported performance reflects a real
    # broker's per-fill cost and the AI rebalancer avoids churning small positions.
    # Applied at the single point where a trade is recorded and accumulated on the
    # session; set to 0 to disable.
    TRANSACTION_COST_USD: float = 1.0

    # Bounded lookback (in years) used when backfilling an asset's daily close
    # history on add, and the window the daily price-history ingestion pass
    # fetches from. Caps backfill cost / provider rate-limit exposure; the
    # Dashboard's per-asset range returns read from whatever history accrues.
    PRICE_HISTORY_BACKFILL_YEARS: int = 5

    # Default benchmark index a newly built paper-trading session is compared
    # against, and the fallback for existing sessions. Must be a valid
    # ``cadence.paper_trading.constants.Benchmark`` id (e.g. "SP500" = S&P 500).
    DEFAULT_BENCHMARK: str = "SP500"

    # Default stop-loss threshold applied when a session opts into the automatic
    # hard stop-loss at build time without specifying its own percentage. Expressed
    # as a fraction of the position's weighted-average cost (0.15 = a 15% drop
    # triggers a whole-position exit). Single threshold for equities and crypto.
    STOP_LOSS_DEFAULT_PCT: float = 0.15

    # How long (in trading days) a stopped-out ticker is quarantined for a session
    # so the daily rebalance cannot immediately re-buy the just-stopped position.
    STOP_LOSS_COOLDOWN_TRADING_DAYS: int = 5

    # Default portfolio risk-guardrail parameters applied when a session opts into
    # the guardrails at build time without specifying its own values. The guardrails
    # deterministically cap the AI's target-weight vector on both the build and the
    # rebalance paths; these are the frozen defaults, expressed as fractions in
    # (0, 1] (and a whole-number count for the position floor).
    #: Maximum fraction of the portfolio any single asset may hold (0.25 = 25%).
    GUARDRAIL_DEFAULT_MAX_ASSET_PCT: float = 0.25
    #: Maximum fraction of the portfolio any single asset class may hold (0.60 = 60%).
    GUARDRAIL_DEFAULT_MAX_ASSET_CLASS_PCT: float = 0.60
    #: Minimum number of positions the AI is asked to hold (a diversification floor;
    #: surfaced/logged rather than fabricated when the AI returns fewer names).
    GUARDRAIL_DEFAULT_MIN_POSITIONS: int = 5
    #: Maximum fraction of the allocated capital that may be invested (the remainder
    #: is held as a cash buffer; 0.95 = keep at least 5% cash).
    GUARDRAIL_DEFAULT_MAX_INVESTED_PCT: float = 0.95

    # Model id the AI portfolio manager runs on.
    AI_PORTFOLIO_MODEL: str = "gpt-5-mini"

    # Cost controls bounding the AI portfolio build/rebalance runs. These cap the
    # number of expensive LLM/tool interactions per job so a single run cannot run
    # away with turns, web searches, or newly-discovered assets.
    #: Hard SDK-enforced turn cap per agent run (bounds tool-call loops). Sized
    #: with headroom above the web-search budget: each search is a turn, plus
    #: planning turns and the extra final model call the structured ``output_type``
    #: forces, so this must exceed ``AI_PORTFOLIO_MAX_WEB_SEARCHES`` comfortably.
    AI_PORTFOLIO_MAX_TURNS: int = 12
    #: Hard cap on web searches per agent run (enforced in the web_search tool).
    AI_PORTFOLIO_MAX_WEB_SEARCHES: int = 6
    #: Cap on assets the agent may discover and add beyond the current universe.
    AI_PORTFOLIO_MAX_NEW_ASSETS: int = 5

    # Shared secret guarding the daily-rebalance trigger. The cron sidecar sends
    # it in the ``X-Cron-Token`` header; the endpoint rejects any request whose
    # header does not match. Empty (the default) means no valid token exists, so
    # every trigger is rejected — the rebalance must be explicitly enabled by
    # configuring a non-empty token.
    REBALANCE_CRON_TOKEN: str = ""

    # Pushover push notifications (optional). Used to notify on daily-rebalance
    # outcomes. Both are optional: when either is empty, notifications are
    # silently disabled and the app still boots and rebalances normally.
    PUSHOVER_USER: str = ""
    PUSHOVER_TOKEN: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS`` to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
