"""Agent tools. A provider-configurable ``web_search`` function tool.

Follows the trading-bot ``agent/tools.py`` pattern: the search is a blocking
call pushed onto a thread and awaited under a timeout. The backend search
provider is chosen by ``settings.WEB_SEARCH_PROVIDER`` — ``serpapi`` (the SerpAPI
SDK, keyed by ``SERP_API_KEY``) or ``serper`` (an HTTP POST to serper.dev, keyed
by ``SERPER_API_KEY``). Each provider raises a clear error when its own key is
missing so a run fails cleanly rather than silently returning nothing; an
unrecognised provider value also raises.

Both providers normalise their raw response to the SAME trimmed shape so the
persisted research transcript and the UI that renders it are unaffected by the
choice. The raw payloads are large (search metadata, pagination, related
questions, ads, …); returning them verbatim on every call floods the agent's
context and, across many searches in one run, overflows the model's context
window. So we trim each response down to the few fields the agent actually needs
— the top organic results plus any answer box / knowledge-graph snippet.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import serpapi
from agents.tool import function_tool

from cadence.config import settings

SEARCH_TIMEOUT_SECONDS = 30

#: Serper (serper.dev) Google-search endpoint used by the ``serper`` provider.
SERPER_SEARCH_URL = "https://google.serper.dev/search"

#: How many organic results to keep per search. Enough to inform the agent
#: without ballooning the context.
MAX_ORGANIC_RESULTS = 5

#: Per-run remaining web-search budget. ``None`` means "unbounded" (no budget was
#: installed for this context); an int is the number of searches still allowed.
#: Set via :func:`web_search_budget` and read/decremented inside the tool. A
#: ``ContextVar`` so the budget follows the async task tree of a single agent run
#: even when tool calls execute on child tasks.
_web_search_budget: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "web_search_budget", default=None
)

#: Message returned by the tool once the budget is exhausted (no SerpAPI call).
BUDGET_EXHAUSTED_MESSAGE = "web search budget exhausted — do not search again"

#: Per-run research log. When a list is installed (via :func:`record_web_searches`),
#: every :func:`web_search` appends a ``{query, results, error}`` entry so the run's
#: research can be persisted for later review. ``None`` means "not recording".
#: A ``ContextVar`` so it follows the async task tree of a single agent run.
#:
#: The recorder only ever *appends* to the shared list (it never rebinds the var),
#: so — unlike the budget, which must be installed inside the run — a recorder
#: installed OUTSIDE ``asyncio.run`` is still seen by tool calls inside it: child
#: task contexts inherit the same list object.
_web_search_log: contextvars.ContextVar[list[dict[str, Any]] | None] = (
    contextvars.ContextVar("web_search_log", default=None)
)


@contextmanager
def web_search_budget(n: int) -> Iterator[None]:
    """Install a hard per-run web-search budget for the enclosed context.

    Wrap an agent run in this context manager to cap the total number of
    :func:`web_search` calls at ``n``. The budget is stored in a ``ContextVar`` so
    the async tool calls the SDK schedules while running the agent inherit it.
    """
    token = _web_search_budget.set(n)
    try:
        yield
    finally:
        _web_search_budget.reset(token)


@contextmanager
def record_web_searches() -> Iterator[list[dict[str, Any]]]:
    """Install a per-run web-search recorder, yielding the growing research log.

    Each :func:`web_search` performed within the context appends a
    ``{query, results, error}`` entry (via :func:`note_web_search`). The yielded
    list is the live log: it is bound at ``with`` entry and keeps accumulating, so
    a caller can persist whatever research was captured even if the enclosed run
    later raises.
    """
    log: list[dict[str, Any]] = []
    token = _web_search_log.set(log)
    try:
        yield log
    finally:
        _web_search_log.reset(token)


def note_web_search(
    query: str, results: dict[str, Any] | None, *, error: str | None = None
) -> None:
    """Append a research entry to the active recorder, if one is installed.

    A no-op when no :func:`record_web_searches` recorder is active, so the tool
    (and test fakes) can call it unconditionally.
    """
    log = _web_search_log.get()
    if log is not None:
        log.append({"query": query, "results": results, "error": error})


def _compact(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Pick ``keys`` from ``source``, dropping empty/missing values."""
    return {key: source[key] for key in keys if source.get(key)}


def _trim_serp_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw SerpAPI Google payload to a small, agent-useful subset."""
    trimmed: dict[str, Any] = {}

    # Surface a SerpAPI-reported error so the agent can react instead of hanging.
    if raw.get("error"):
        trimmed["error"] = raw["error"]

    organic = raw.get("organic_results")
    if isinstance(organic, list):
        trimmed["organic_results"] = [
            _compact(item, ("title", "link", "snippet"))
            for item in organic[:MAX_ORGANIC_RESULTS]
            if isinstance(item, dict)
        ]

    answer_box = raw.get("answer_box")
    if isinstance(answer_box, dict):
        compact = _compact(answer_box, ("title", "answer", "snippet"))
        if compact:
            trimmed["answer_box"] = compact

    knowledge_graph = raw.get("knowledge_graph")
    if isinstance(knowledge_graph, dict):
        compact = _compact(knowledge_graph, ("title", "type", "description"))
        if compact:
            trimmed["knowledge_graph"] = compact

    return trimmed


def _trim_serper_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a raw Serper (serper.dev) Google payload to the shared trimmed shape.

    Serper uses different top-level keys than SerpAPI (``organic`` /
    ``answerBox`` / ``knowledgeGraph``); this maps them onto the exact same
    ``organic_results`` / ``answer_box`` / ``knowledge_graph`` shape
    :func:`_trim_serp_payload` emits, so downstream consumers see one shape
    regardless of provider.
    """
    trimmed: dict[str, Any] = {}

    # Surface a backend-reported error so the agent can react instead of hanging.
    if raw.get("error"):
        trimmed["error"] = raw["error"]

    organic = raw.get("organic")
    if isinstance(organic, list):
        trimmed["organic_results"] = [
            _compact(item, ("title", "link", "snippet"))
            for item in organic[:MAX_ORGANIC_RESULTS]
            if isinstance(item, dict)
        ]

    answer_box = raw.get("answerBox")
    if isinstance(answer_box, dict):
        compact = _compact(answer_box, ("title", "answer", "snippet"))
        if compact:
            trimmed["answer_box"] = compact

    knowledge_graph = raw.get("knowledgeGraph")
    if isinstance(knowledge_graph, dict):
        compact = _compact(knowledge_graph, ("title", "type", "description"))
        if compact:
            trimmed["knowledge_graph"] = compact

    return trimmed


def _search_serpapi(query: str) -> dict[str, Any]:
    """Run a blocking SerpAPI Google search and return the trimmed payload.

    Raises ``ValueError`` when ``SERP_API_KEY`` is unset so a run fails cleanly.
    """
    serp_api_key = settings.SERP_API_KEY
    if not serp_api_key:
        raise ValueError(
            "SERP_API_KEY is not set. Add it to your environment or .env file."
        )

    client = serpapi.Client(api_key=serp_api_key)
    results = client.search(
        {
            "engine": "google",
            "q": query,
            "google_domain": "google.com",
            "hl": "en",
            "gl": "us",
            "num": MAX_ORGANIC_RESULTS,
        }
    )
    raw: dict[str, Any] = results.as_dict()
    return _trim_serp_payload(raw)


def _search_serper(query: str) -> dict[str, Any]:
    """Run a blocking Serper (serper.dev) Google search and return the trimmed payload.

    Raises ``ValueError`` when ``SERPER_API_KEY`` is unset so a run fails cleanly.
    A non-200 response or transport error is converted to an ``{"error": ...}``
    result — mirroring how a SerpAPI error surfaces — so the agent sees a uniform
    error field rather than an exception.
    """
    serper_api_key = settings.SERPER_API_KEY
    if not serper_api_key:
        raise ValueError(
            "SERPER_API_KEY is not set. Add it to your environment or .env file."
        )

    try:
        response = httpx.post(
            SERPER_SEARCH_URL,
            headers={"X-API-KEY": serper_api_key},
            json={"q": query, "num": MAX_ORGANIC_RESULTS, "gl": "us", "hl": "en"},
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return {"error": f"Serper request failed: {exc}"}

    if response.status_code != httpx.codes.OK:
        return {"error": f"Serper returned HTTP {response.status_code}"}

    raw: dict[str, Any] = response.json()
    return _trim_serper_payload(raw)


async def _run_web_search(query: str) -> dict[str, Any]:
    """Core web-search implementation shared by the tool and its unit tests.

    Honors the per-run budget installed by :func:`web_search_budget`: once the
    budget is exhausted this returns an error dict WITHOUT contacting any
    provider, so a run cannot exceed its configured search cap. When a budget is
    set and has remaining capacity it is decremented before the search proceeds.

    Dispatches on :data:`settings.WEB_SEARCH_PROVIDER` to the SerpAPI or Serper
    backend; an unrecognised value raises ``ValueError``. Both providers are run
    on a worker thread under the shared timeout and normalise to the same trimmed
    shape before being recorded in the research log.
    """
    remaining = _web_search_budget.get()
    if remaining is not None:
        if remaining <= 0:
            note_web_search(query, None, error=BUDGET_EXHAUSTED_MESSAGE)
            return {"error": BUDGET_EXHAUSTED_MESSAGE}
        _web_search_budget.set(remaining - 1)

    provider = settings.WEB_SEARCH_PROVIDER
    if provider == "serpapi":
        search = _search_serpapi
    elif provider == "serper":
        search = _search_serper
    else:
        raise ValueError(
            f"WEB_SEARCH_PROVIDER has an unrecognised value {provider!r}; "
            "expected 'serpapi' or 'serper'."
        )

    loop = asyncio.get_event_loop()
    trimmed = await asyncio.wait_for(
        loop.run_in_executor(None, search, query),
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    note_web_search(query, trimmed, error=trimmed.get("error"))
    return trimmed


@function_tool(
    description_override=(
        "Search Google (via the configured provider, SerpAPI or Serper) and "
        "return the top organic results (title, link, snippet) plus any answer "
        "box or knowledge-graph snippet."
    )
)
async def web_search(query: str) -> dict[str, Any]:
    """Search the web for the given query and return a trimmed result set."""
    return await _run_web_search(query)
