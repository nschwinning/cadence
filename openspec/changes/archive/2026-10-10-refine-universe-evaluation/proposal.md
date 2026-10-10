## Why

The asset-universe evaluation agent recommends instruments Cadence can never hold. It recently suggested "introduce fixed-income and cash-equivalent instruments or ETFs" — but Cadence's universe is deliberately limited to US Alpaca-tradable **individual stocks and crypto** (`SUPPORTED_CATEGORIES = {STOCK, CRYPTO}`; ETF/FUND quote types are detected only to reject them at add time). The agent gives generically-sound portfolio advice that is blind to this constraint, so its suggestions are unactionable: the operator cannot act on advice to add an ETF or a bond fund. We evaluated and explicitly decided **not** to build ETF/fixed-income support (daily-rebalanced TA timing shows marginal, unproven benefit for this stack, and bond instruments collide with Cadence's price-only valuation). The fix is to make the prompt scope-aware so its suggestions stay in-scope.

Separately, the "Universe evaluation" panel on the Assets page is always fully expanded and can be long, pushing the asset table down. Making it collapsible lets the operator hide it once read.

## What Changes

- **Scope-aware evaluation prompt** — the universe-evaluation agent prompt (both the system instructions and the per-summary input) is told Cadence's scope: the universe may only hold US Alpaca-tradable individual equities and crypto, managed long-only with full-universe weighting (no shorting/leverage/options/derivatives), and cannot hold ETFs, mutual/bond/money-market funds, fixed-income instruments, cash-equivalents, or foreign (non-US-listed) securities. Suggestions must therefore stay in-scope — add specific stocks/crypto, rebalance sectors, reduce concentration, or resolve foreign/unpriceable listings to their US listing/ADR — and must not propose any unsupported instrument class.
- **Collapsible evaluation panel** — the panel gains a disclosure toggle in its header (`aria-expanded`/`aria-controls`) that shows/hides the body. Defaults to expanded (current behavior); the header and Refresh control stay visible when collapsed.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `assets`: the universe-evaluation requirement is refined so the generated evaluation respects Cadence's supported scope — its suggestions stay within the US-tradable stocks-and-crypto, long-only universe and never recommend unsupported instrument classes.
- `app-shell`: the Assets-page universe-evaluation view requirement is refined so the evaluation section is collapsible.

## Impact

- **Backend (`assets`):** prompt text only in `backend/src/cadence/assets/universe_agent.py` (`_AGENT_INSTRUCTIONS` + `build_universe_evaluation_prompt`), plus its unit test. No schema, model, migration, API, or summary-building change; the structured `UniverseEvaluationOutput` and the agent's tool-less, score-free behavior are unchanged.
- **Frontend (`app-shell`):** `frontend/src/pages/assets/UniverseEvaluationPanel.tsx` gains local collapse state (`useState`) and a header toggle, plus a co-located vitest. No API/type change.
- **Out of scope:** building ETF/fixed-income support; any change to `SUPPORTED_CATEGORIES`, the recommender/rebalance agents, valuation, or `UniverseSummary`/`_universe_summary`; persisting collapse state across reloads; any migration/schema/API change.
- **Verify gates:** backend `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`; frontend `cd frontend && npm run typecheck && npx vitest run && npm run build`.
