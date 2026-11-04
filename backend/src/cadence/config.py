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
    # Optional LiteLLM model-gateway proxy. When ``LITELLM_BASE_URL`` is set, all
    # agent LLM calls are routed through that OpenAI-compatible proxy, which maps
    # each model id to its provider (OpenAI for ``gpt-*``, Anthropic for
    # ``claude-*``) and records per-request token usage/cost. ``LITELLM_API_KEY``
    # is the proxy's master/virtual key. Empty base URL (the default) DISABLES the
    # gateway entirely: the SDK keeps its implicit OpenAI client and behavior —
    # including the offline stubs and tests — is unchanged. The provider API keys
    # (OpenAI, Anthropic) live on the proxy, not here.
    LITELLM_BASE_URL: str = ""
    LITELLM_API_KEY: str = ""
    # Optional read-only connection to the LiteLLM proxy's spend-log database
    # (``LiteLLM_SpendLogs``), used solely to surface per-session AI cost as a
    # KPI. Independent of ``LITELLM_BASE_URL``: routing can be on without cost
    # surfacing, or vice-versa. Empty (the default) DISABLES the cost KPI — it
    # is reported as absent and the spend DB is never queried. This is a secret
    # (a DSN with a password) and is never surfaced in any response or status.
    LITELLM_DATABASE_URL: str = ""
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

    # SEC EDGAR fundamentals provider (used when creating watchlist assets).
    # EDGAR requires a descriptive User-Agent identifying the caller (name +
    # contact); set a real one in deployment. Fetching is best-effort and never
    # fails asset creation, so a placeholder here degrades gracefully to
    # "fundamentals unavailable" rather than erroring.
    SEC_EDGAR_USER_AGENT: str = "Cadence (paper-trading research) contact@example.com"
    #: Base URL for the SEC static files (ticker→CIK map) and the data API.
    SEC_EDGAR_WWW_BASE_URL: str = "https://www.sec.gov"
    SEC_EDGAR_DATA_BASE_URL: str = "https://data.sec.gov"
    #: Wall-clock ceiling (seconds) for a single EDGAR HTTP request.
    SEC_EDGAR_TIMEOUT_SECONDS: float = 10.0

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

    # Asset-class-aware transaction cost charged on every executed paper trade,
    # matching Alpaca's real fee schedule: US equities/ETFs are commission-free
    # (market-order slippage is already in the fill price), while crypto incurs a
    # percentage taker fee on the executed notional. This is the crypto taker fee
    # as a fraction of notional (0.0025 = 0.25%, Alpaca base tier); equities are
    # charged nothing. Applied at the single point where a trade is recorded and
    # accumulated on the session; set to 0 to disable the crypto fee.
    CRYPTO_FEE_PCT: float = 0.0025

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

    # Default learning-feedback window applied when a session opts into learning
    # feedback at build time without specifying its own window. Number of recent
    # daily-run snapshots the rebalance agent is shown (5 ≈ a trading week). This is
    # a build-form default / fallback only — it is never read at rebalance time
    # (rebalance always uses the session's frozen ``learning_feedback_window``).
    LEARNING_FEEDBACK_DEFAULT_WINDOW: int = 5

    # Default model id the AI portfolio manager runs on when a session does not
    # select one (new builds freeze a per-session model from the fixed catalog in
    # paper_trading.constants.AIModel). Must be a catalog member.
    AI_PORTFOLIO_MODEL: str = "gpt-6-luna"

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

    # Price-ML signal: a pooled gradient-boosted classifier predicting the sign of
    # each asset's forward-return over PRICE_ML_HORIZON_DAYS trading days. These
    # knobs are read by the nightly precompute and the rebalance-time annotation.
    #: Forward-return horizon the model is trained to predict (trading days).
    PRICE_ML_HORIZON_DAYS: int = 21
    #: Retrain cadence (calendar days). The precompute reuses the cached model
    #: until it is older than this, then retrains — so predictions stay stable
    #: between retrains (default weekly).
    PRICE_ML_RETRAIN_DAYS: int = 7
    #: Minimum stored daily bars an asset needs before it is trained/predicted on.
    #: Must comfortably exceed the longest moving-average window plus the horizon.
    PRICE_ML_MIN_BAR_COUNT: int = 260
    #: A stored signal older than this many days (relative to the rebalance's
    #: as-of date) is treated as stale and rendered "unavailable".
    PRICE_ML_STALENESS_DAYS: int = 7
    #: Fixed random seed for deterministic training and walk-forward evaluation.
    PRICE_ML_SEED: int = 42
    #: Model/feature-schema version stored with each signal and gating the cache.
    PRICE_ML_MODEL_VERSION: str = "price-ml-v1"
    #: Directory holding the cached trained model artifact (joblib).
    PRICE_ML_MODEL_DIR: str = "var/price_ml"

    # News sentiment: a FinBERT-lineage tone signal classifying recent headlines
    # into positive / neutral / negative, served OUT-OF-PROCESS via a sentiment
    # sidecar reached behind the ``SentimentScorer`` protocol (the backend never
    # loads the model). These knobs are read at rebalance time when a session opted
    # into the signal.
    #: Base URL of the sentiment-scoring sidecar. Empty (the default) DISABLES the
    #: feature entirely — every ticker degrades to "unavailable" — so the signal is
    #: opt-in via deployment config, mirroring how an unset provider URL disables.
    SENTIMENT_SERVICE_URL: str = ""
    #: Per-request timeout (seconds) for calls to the sentiment-scoring sidecar.
    SENTIMENT_SERVICE_TIMEOUT_SECONDS: float = 10.0
    #: Trailing window (calendar days) of news scored for each ticker's tone
    #: aggregate (default ~3 days). News older than this is ignored.
    SENTIMENT_WINDOW_DAYS: int = 3
    #: Exponential recency half-life (days) weighting news within the window: an
    #: item this many days old carries half the weight of a same-day item, so more
    #: recent headlines dominate the aggregate.
    SENTIMENT_RECENCY_HALFLIFE_DAYS: float = 1.5
    #: Neutral band for classifying the recency-weighted (positive − negative)
    #: aggregate: within ±this is "neutral", strictly above "positive", strictly
    #: below "negative".
    SENTIMENT_NEUTRAL_BAND: float = 0.15
    #: Maximum news items fetched per ticker per window (bounds the scoring batch).
    SENTIMENT_MAX_ARTICLES: int = 50
    #: Base URL of the Alpaca News API used as the news source (reuses the Alpaca
    #: credentials above).
    ALPACA_NEWS_BASE_URL: str = "https://data.alpaca.markets/v1beta1/news"

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

    # Rebalance order sequencing (sells-before-buys fill gate). During a
    # rebalance the executor submits every sell first, waits for the submitted
    # sells to reach a terminal state at the broker, then submits the buys. The
    # wait is bounded by ``REBALANCE_SELL_FILL_TIMEOUT_SECONDS`` and polled every
    # ``REBALANCE_SELL_FILL_POLL_SECONDS``; on timeout the dependent buys are
    # withheld (fail-safe). ``REBALANCE_ORDER_MAX_ATTEMPTS`` bounds in-run retries
    # of a rejected order. Under the immediate-fill stub, sells settle on the
    # first poll so the timeout is never exercised.
    REBALANCE_SELL_FILL_TIMEOUT_SECONDS: float = 30.0
    REBALANCE_SELL_FILL_POLL_SECONDS: float = 1.0
    REBALANCE_ORDER_MAX_ATTEMPTS: int = 3

    # Cash buffer reserved before sizing build and rebalance orders so a fully
    # invested target (weights summing to ~1.0) does not deploy 100% of the
    # session's value and then overdraw on per-trade fees and market-order fill
    # slippage, driving unallocated cash negative. The reserved amount is the
    # GREATER of this fraction of the sizing base and the estimated crypto trade
    # fees for the run (``CRYPTO_FEE_PCT`` * the base when the run includes any
    # crypto candidate, else 0 — equities are free); the base is reduced by that
    # reserve before any target weight is applied. Set to 0 (together with
    # ``CRYPTO_FEE_PCT`` = 0) to disable the reserve.
    REBALANCE_CASH_BUFFER_PCT: float = 0.015

    # Strategy-bot subsystem. A parallel, deterministic (non-AI) bot domain whose
    # cron-triggered intraday ``/tick`` runs a pure technical strategy over a single
    # universe asset. The cron *schedule strings* live in docker-compose/env (like
    # REBALANCE_SCHEDULE); the knobs below are tunable Pydantic settings.
    #: Tick interval in minutes — how often ``/bots/tick`` fires. Decoupled from the
    #: signal bar timeframe so exit checks can run more often than entry computation.
    #: Advisory/documentation value; the actual firing cadence is the cron string.
    BOT_TICK_INTERVAL_MINUTES: int = 5
    #: Bar timeframe (an Alpaca ``BarTimeframe`` value) the strategy computes signals
    #: on. Default 5-minute bars.
    BOT_SIGNAL_BAR_TIMEFRAME: str = "5Min"
    #: Retention window (days) for intraday ``bot_value_points``. The daily snapshot
    #: job prunes points older than this, bounding intraday storage. Because the
    #: ``5min`` and ``hourly`` chart resolutions read these points, both span roughly
    #: this window; ``daily``/``monthly`` come from daily snapshots and stay unbounded.
    BOT_VALUE_POINT_RETENTION_DAYS: int = 30
    #: Market-data feed (a ``MarketDataFeed`` value) the tick requests bars with. The
    #: tick ALWAYS sets this explicitly rather than relying on the account default.
    #: ``iex`` is real-time on the free tier; ``sip`` requires a paid subscription.
    BOT_MARKET_DATA_FEED: str = "iex"
    #: Data-source mode: ``rest`` pulls bars on demand per tick (verified real-time
    #: via ``feed=iex``); ``stream`` would read a collector-backed cache. v1 ships
    #: ``rest`` only; the setting reserves the seam.
    BOT_MARKET_DATA_MODE: str = "rest"
    #: Freshness bound (minutes): the most-recent bar must be no older than this
    #: many minutes past its timeframe for the tick to act; otherwise the session is
    #: skipped (IEX can produce sparse/missing recent bars). ~2 bar widths.
    BOT_BAR_FRESHNESS_MINUTES: int = 10
    #: Default cash buffer reserved before a bot's all-in sizing (fraction of
    #: allocated capital) when a session does not specify its own.
    BOT_CASH_BUFFER_PCT: float = 0.02
    #: Default drawdown kill-switch threshold (fraction of peak value) applied when a
    #: session does not specify its own. A fall of this fraction from the running
    #: peak exits the position and stops the session.
    BOT_DRAWDOWN_STOP_PCT: float = 0.25
    #: Default position-sizing method (a ``SizingMethod`` value) for a new bot that
    #: does not specify its own. New multi-asset bots default to ATR risk-based sizing.
    BOT_SIZING_METHOD: str = "atr_risk"
    #: Default fraction of the budget risked per position under ATR sizing.
    BOT_RISK_PCT: float = 0.01
    #: Default ATR lookback period (number of bars) for ATR risk-based sizing.
    BOT_ATR_PERIOD: int = 14
    #: Default ATR multiple defining per-share risk under ATR risk-based sizing.
    BOT_ATR_K: float = 2.0
    #: Default maximum fraction of the budget any single position may consume.
    BOT_MAX_POSITION_PCT: float = 0.25
    #: Default maximum number of concurrent open positions per bot session.
    BOT_MAX_POSITIONS: int = 10

    # Per-probe timeout (seconds) for the system-status endpoint. Each external
    # backend is live-probed concurrently; a probe that exceeds this bound is
    # reported as unreachable with a timeout detail so a slow or hung backend can
    # never delay the overall /system/status response beyond roughly this value.
    SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS: float = 5.0

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS`` to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
