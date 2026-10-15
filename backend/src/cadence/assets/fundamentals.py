"""Company fundamentals access behind a thin, testable interface.

All network access is confined to :class:`SecEdgarFundamentalsProvider`. The rest
of the domain depends only on the :class:`FundamentalsProvider` protocol, so tests
inject a fake and never touch the network.

EDGAR is equities-only (US filers), so fundamentals are fetched for stock
watchlist assets. Fetching is deliberately best-effort: a missing CIK, missing
facts, or a network error yields a :class:`Fundamentals` with
``status = UNAVAILABLE`` rather than raising, so it can never fail asset creation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import httpx

from cadence.config import settings

logger = logging.getLogger(__name__)

#: Identifies the data source on a persisted fundamentals row.
SOURCE_SEC_EDGAR = "sec_edgar"


class FundamentalsStatus(StrEnum):
    """Whether a fundamentals fetch produced usable data.

    ``AVAILABLE`` — the core figures were found. ``PARTIAL`` — a CIK resolved and
    some, but not all, core figures were found. ``UNAVAILABLE`` — no CIK, no
    usable facts, or the provider was unreachable (creation still succeeded).
    """

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Fundamentals:
    """Raw company fundamentals mapped from a provider (no derivation).

    ``document`` holds the mapped figures and company details as a JSON-safe
    dict; ``status`` records the fetch outcome and ``cik`` the resolved EDGAR
    identifier (when known). ``source`` names the provider for the persisted row.
    """

    status: FundamentalsStatus
    source: str
    cik: str | None = None
    document: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(
        cls, source: str = SOURCE_SEC_EDGAR, *, cik: str | None = None
    ) -> Fundamentals:
        """A no-data result carrying only the attempt's source/CIK."""
        return cls(status=FundamentalsStatus.UNAVAILABLE, source=source, cik=cik)


@runtime_checkable
class FundamentalsProvider(Protocol):
    """Seam for fetching company fundamentals.

    Implemented by :class:`SecEdgarFundamentalsProvider` in production and by a
    fake in tests. ``fetch_fundamentals`` is synchronous so the services stay
    fully sync and never raises — a failed fetch returns an ``UNAVAILABLE``
    result.
    """

    def fetch_fundamentals(self, ticker: str) -> Fundamentals:
        """Return fundamentals for ``ticker`` (never raises)."""
        ...


# EDGAR US-GAAP concept -> the document key we persist it under. Revenue has two
# common concepts across filers; the first present one wins.
_REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
_FIGURE_CONCEPTS: dict[str, str] = {
    "gross_profit": "GrossProfit",
    "operating_income": "OperatingIncomeLoss",
    "net_income": "NetIncomeLoss",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "eps_basic": "EarningsPerShareBasic",
    "eps_diluted": "EarningsPerShareDiluted",
}


class SecEdgarFundamentalsProvider:
    """Production :class:`FundamentalsProvider` backed by SEC EDGAR.

    Resolves the ticker to a CIK via EDGAR's published ``company_tickers.json``,
    then reads the company's XBRL facts (``companyfacts``) and recent filing
    metadata (``submissions``) to map the core figures and company details.
    Confines all HTTP to this class and never raises: any failure degrades to an
    ``UNAVAILABLE`` (or ``PARTIAL``) result and is logged.
    """

    def __init__(self) -> None:
        # Per-instance cache of the (large) ticker->CIK map so a multi-candidate
        # run fetches it once.
        self._ticker_to_cik: dict[str, str] | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": settings.SEC_EDGAR_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }

    def _get_json(self, url: str) -> Any:
        response = httpx.get(
            url,
            headers=self._headers(),
            timeout=settings.SEC_EDGAR_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    def _load_ticker_map(self) -> dict[str, str]:
        """Return (and cache) the upper-cased ticker -> 10-digit CIK map."""
        if self._ticker_to_cik is not None:
            return self._ticker_to_cik
        url = f"{settings.SEC_EDGAR_WWW_BASE_URL}/files/company_tickers.json"
        data = self._get_json(url)
        mapping: dict[str, str] = {}
        # The file is a JSON object keyed by row index; each value has
        # ``cik_str`` (int) and ``ticker``.
        for row in data.values():
            ticker = str(row.get("ticker", "")).strip().upper()
            cik_str = row.get("cik_str")
            if ticker and cik_str is not None:
                mapping[ticker] = f"{int(cik_str):010d}"
        self._ticker_to_cik = mapping
        return mapping

    def _resolve_cik(self, ticker: str) -> str | None:
        """Resolve ``ticker`` to a zero-padded CIK, or ``None`` if unknown."""
        normalized = ticker.strip().upper()
        mapping = self._load_ticker_map()
        if normalized in mapping:
            return mapping[normalized]
        # EDGAR lists class shares with a dash (e.g. ``BRK-B``); callers may store
        # a dot. Try the dash form as a fallback.
        return mapping.get(normalized.replace(".", "-"))

    def fetch_fundamentals(self, ticker: str) -> Fundamentals:
        try:
            cik = self._resolve_cik(ticker)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("EDGAR ticker map fetch failed for %s: %s", ticker, exc)
            return Fundamentals.unavailable()
        if cik is None:
            return Fundamentals.unavailable()

        try:
            facts = self._get_json(
                f"{settings.SEC_EDGAR_DATA_BASE_URL}"
                f"/api/xbrl/companyfacts/CIK{cik}.json"
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("EDGAR companyfacts fetch failed for %s: %s", ticker, exc)
            return Fundamentals.unavailable(cik=cik)

        document = _map_company_facts(facts)
        document["company_details"] = self._fetch_company_details(cik, facts)

        figures = document.get("figures", {})
        if not figures:
            status = FundamentalsStatus.UNAVAILABLE
        elif "revenue" in figures and len(figures) >= len(_FIGURE_CONCEPTS):
            status = FundamentalsStatus.AVAILABLE
        else:
            status = FundamentalsStatus.PARTIAL
        return Fundamentals(
            status=status,
            source=SOURCE_SEC_EDGAR,
            cik=cik,
            document=document,
        )

    def _fetch_company_details(
        self, cik: str, facts: dict[str, Any]
    ) -> dict[str, Any]:
        """Best-effort company details from submissions, falling back to facts."""
        details: dict[str, Any] = {"entity_name": facts.get("entityName")}
        try:
            submissions = self._get_json(
                f"{settings.SEC_EDGAR_DATA_BASE_URL}/submissions/CIK{cik}.json"
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, exc)
            return details
        for key in ("name", "sic", "sicDescription", "exchanges", "tickers"):
            if key in submissions:
                details[key] = submissions[key]
        return details


def _latest_annual_value(unit_series: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most recent annual (10-K/FY) data point from a unit series.

    Prefers annual filings (``form`` 10-K and fiscal period ``FY``); within those
    the one with the latest ``end`` date wins. Falls back to the overall latest
    ``end`` when no annual point is present.
    """
    annual = [
        point
        for point in unit_series
        if point.get("form") == "10-K" and point.get("fp") == "FY"
    ]
    pool = annual or unit_series
    if not pool:
        return None
    return max(pool, key=lambda point: str(point.get("end", "")))


def _concept_value(
    us_gaap: dict[str, Any], concept: str
) -> dict[str, Any] | None:
    """Return the latest annual value + period for a US-GAAP concept, if present."""
    concept_facts = us_gaap.get(concept)
    if not concept_facts:
        return None
    units = concept_facts.get("units", {})
    # Prefer USD; otherwise take the first available unit (e.g. USD/shares for EPS).
    unit_key = "USD" if "USD" in units else next(iter(units), None)
    if unit_key is None:
        return None
    point = _latest_annual_value(units[unit_key])
    if point is None or "val" not in point:
        return None
    return {
        "value": point["val"],
        "unit": unit_key,
        "fiscal_year": point.get("fy"),
        "period_end": point.get("end"),
        "form": point.get("form"),
    }


def _map_company_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Map raw EDGAR companyfacts into our persisted ``figures`` document."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    figures: dict[str, Any] = {}

    for concept in _REVENUE_CONCEPTS:
        revenue = _concept_value(us_gaap, concept)
        if revenue is not None:
            figures["revenue"] = revenue
            break

    for key, concept in _FIGURE_CONCEPTS.items():
        value = _concept_value(us_gaap, concept)
        if value is not None:
            figures[key] = value

    return {"figures": figures}
