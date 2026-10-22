"""Live compatibility spike for the LiteLLM model-gateway (OpenSpec task 6.1).

Drives one real agent run through the configured LiteLLM proxy and checks the
combination the spike exists to de-risk: a mandatory Pydantic ``output_type``
*together with* the ``web_search`` function tool. It confirms the agent returns a
schema-valid structured result while making at least one tool call, and (when the
proxy's Postgres SpendLogs are reachable) that a usage/cost row was captured and
carries the run's trace id.

Run it wherever the provider keys live (the deployment Pi, or locally once the
keys are in ``.env``), with the proxy already up:

    # Gateway on, pointed at the running proxy:
    export LITELLM_BASE_URL=http://localhost:4000   # or http://litellm:4000
    export LITELLM_API_KEY=<proxy master/virtual key>
    # The web_search tool needs its provider key (same as the app):
    export WEB_SEARCH_PROVIDER=serpapi
    export SERP_API_KEY=<key>
    # Pick the catalog model alias to route (gpt-* -> OpenAI, claude-* -> Anthropic):
    uv run python scripts/litellm_spike.py --model gpt-5-mini

    # Optional: verify the spend-log row by passing the proxy's DB URL:
    uv run python scripts/litellm_spike.py --model gpt-5-mini \
        --spend-db postgresql://cadence:cadence@localhost:5435/litellm

Exit code 0 = schema-valid output with >=1 tool call; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from agents.items import ToolCallItem
from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent, configure_model_gateway, gateway_enabled, llm_trace
from cadence.agents.tools import web_search, web_search_budget


class _SpikeOutput(BaseModel):
    """A small flat structured output, mirroring the real agents' shape."""

    summary: str = Field(description="One sentence on what you found.")
    tickers: list[str] = Field(default_factory=list, description="Any tickers mentioned.")


_INSTRUCTIONS = (
    "You are a markets research assistant. Use the web_search tool at least once "
    "to look up a recent fact about the US stock market, then return the structured "
    "result. You MUST call web_search before answering."
)


async def _run(model: str, trace_id: str) -> tuple[_SpikeOutput, int]:
    agent = build_agent(
        name="LiteLLMSpikeAgent",
        instructions=_INSTRUCTIONS,
        output_type=_SpikeOutput,
        tools=[web_search],
        model=model,
    )
    with web_search_budget(3), llm_trace(trace_id):
        result = await Runner.run(
            agent,
            "What is one notable thing that happened in the US stock market recently?",
            max_turns=5,
        )
    tool_calls = sum(1 for item in result.new_items if isinstance(item, ToolCallItem))
    output: _SpikeOutput = result.final_output
    return output, tool_calls


def _check_spend_log(spend_db: str, trace_id: str) -> None:
    """Best-effort: confirm a SpendLogs row was written for this trace id."""
    try:
        import psycopg
    except ImportError:  # pragma: no cover - optional path
        print("  (psycopg not available; skipping spend-log check)")
        return
    try:
        with psycopg.connect(spend_db, connect_timeout=5) as conn, conn.cursor() as cur:
            # LiteLLM stores request metadata as JSONB; match our trace id.
            cur.execute(
                "SELECT model, total_tokens, spend "
                'FROM "LiteLLM_SpendLogs" '
                "WHERE metadata::text LIKE %s "
                "ORDER BY \"startTime\" DESC LIMIT 1",
                (f"%{trace_id}%",),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"  spend-log check failed: {exc}")
        return
    if row is None:
        print(f"  NO spend-log row found carrying trace id {trace_id!r}")
    else:
        model, tokens, spend = row
        print(f"  spend-log row: model={model} total_tokens={tokens} spend=${spend}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-5-mini", help="Catalog model alias to route.")
    parser.add_argument(
        "--spend-db",
        default="",
        help="Optional Postgres URL of the proxy's litellm DB to verify SpendLogs.",
    )
    args = parser.parse_args()

    if not configure_model_gateway() or not gateway_enabled():
        print("LITELLM_BASE_URL is not set — the gateway is disabled. Set it first.")
        return 2

    trace_id = f"spike-{int(time.time())}"
    print(f"Routing model {args.model!r} through the proxy (trace id {trace_id!r})...")
    try:
        output, tool_calls = asyncio.run(_run(args.model, trace_id))
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        print(f"FAIL: run raised {type(exc).__name__}: {exc}")
        return 1

    print(f"  structured output: {output.model_dump_json()}")
    print(f"  tool calls made: {tool_calls}")
    ok = isinstance(output, _SpikeOutput) and tool_calls >= 1
    if args.spend_db:
        _check_spend_log(args.spend_db, trace_id)

    if ok:
        print("PASS: schema-valid structured output WITH at least one tool call.")
        return 0
    print("FAIL: expected a schema-valid output with >=1 tool call.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
