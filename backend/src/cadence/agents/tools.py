"""Agent tools. Currently a SerpAPI-backed ``web_search`` function tool.

Follows the trading-bot ``agent/tools.py`` pattern: the search is a blocking
SerpAPI call pushed onto a thread and awaited under a timeout, gated on
``SERP_API_KEY``. The tool raises a clear error when the key is missing so a run
fails cleanly rather than silently returning nothing.

The raw SerpAPI payload is large (search metadata, pagination, related
questions, ads, …). Returning it verbatim on every call floods the agent's
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

import serpapi
from agents.tool import function_tool

from cadence.config import settings

SEARCH_TIMEOUT_SECONDS = 30

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


async def _run_web_search(query: str) -> dict[str, Any]:
    """Core web-search implementation shared by the tool and its unit tests.

    Honors the per-run budget installed by :func:`web_search_budget`: once the
    budget is exhausted this returns an error dict WITHOUT contacting SerpAPI, so
    a run cannot exceed its configured search cap. When a budget is set and has
    remaining capacity it is decremented before the search proceeds.
    """
    remaining = _web_search_budget.get()
    if remaining is not None:
        if remaining <= 0:
            return {"error": BUDGET_EXHAUSTED_MESSAGE}
        _web_search_budget.set(remaining - 1)

    serp_api_key = settings.SERP_API_KEY
    if not serp_api_key:
        raise ValueError(
            "SERP_API_KEY is not set. Add it to your environment or .env file."
        )

    def _search() -> dict[str, Any]:
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

    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _search),
        timeout=SEARCH_TIMEOUT_SECONDS,
    )


@function_tool(
    description_override=(
        "Search Google via SerpAPI and return the top organic results "
        "(title, link, snippet) plus any answer box or knowledge-graph snippet."
    )
)
async def web_search(query: str) -> dict[str, Any]:
    """Search the web for the given query and return a trimmed result set."""
    return await _run_web_search(query)
