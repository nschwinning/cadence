## Why

AI paper-trading sessions persistently strand a large fraction of capital as idle cash. A live session (technical indicators ON, guardrails OFF, $10k) sat at **38% cash ($3,841 of $10,110)** with every rebalance returning status `partial` for ten consecutive runs. The cause is in the executor: target weights are normalized to sum to 1.0 over the AI's target list *before* execution, but when individual targets cannot be executed — no price available, or the per-name budget cannot afford even one whole share — their weight is simply dropped and **never redistributed** to the names that *can* fill. Because the agent keeps re-selecting the same unexecutable tickers (a foreign listing, `ASML.AS`, was targeted at 15% and failed "No price available" on every single run), the shortfall becomes cash and never heals. This defeats the point of a paper-trading strategy: capital the strategy intends to deploy sits uninvested indefinitely.

## What Changes

- **Redeploy unexecutable target weight across the executable set (primary fix).** During a rebalance, after each target's price and one-share affordability are known, redistribute the weight of targets that cannot be executed (unpriceable, or whose budget cannot buy ≥1 share/min-notional) onto the targets that can, so the intended capital is actually deployed rather than stranded. Redistribution stays bounded by the existing reserved cash buffer (`REBALANCE_CASH_BUFFER_PCT`) and continues to respect the risk guardrails when a session has them enabled.
- **Record unexecutable targets explicitly.** A target whose weight cannot be placed (today a silent no-op for the "too small for one share" case) is surfaced as a non-executed result with a clear reason, so `partial`-status runs are explainable from `run_stats`.
- **Stop re-selecting known-unexecutable tickers at rebalance time (folded in).** Gate the agent's candidate universe at rebalance so tickers that cannot be priced/traded (e.g. dot-suffixed foreign listings like `ASML.AS`) are not repeatedly offered to the agent and re-targeted every run. This is coordinated with — not a duplicate of — the separately planned "verify tradability via Alpaca at add-time" work; here the concern is not re-offering a known-unexecutable name during rebalance candidate assembly.
- Out of scope (documented follow-up, **not** implemented here): full fractional-equity-share support, which would remove whole-share flooring entirely.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: The rebalance sizing behavior changes — unexecutable target weight is redeployed across executable targets (bounded by the reserved cash buffer and the risk guardrails) instead of being dropped to cash, and unexecutable targets are recorded with an explicit reason. Rebalance candidate assembly excludes tickers already known to be unexecutable so they are not re-targeted every run.

## Impact

- **Code:** `backend/src/cadence/ai_portfolio/executor.py` (`execute_rebalance` weight handling / per-ticker sizing; a redeployment pass over executable targets). `backend/src/cadence/ai_portfolio/service.py` (rebalance candidate assembly / gating of known-unexecutable tickers; threading any needed context). Possibly `build_agent`/prompt plumbing only if candidate filtering lives there.
- **Behavioral, not schema:** expected to need **no DB migration** and **no frontend/app-shell change** — confirm during design. The observable effect is higher invested fraction (less idle cash) and clearer `run_stats` for skipped targets.
- **Tests:** executor rebalance tests for redeployment (unpriceable target, too-small-for-one-share target, all-but-one unexecutable), guardrail-on interaction, and the no-deployable-cash skip path remaining intact; service tests for rebalance candidate gating.
- **Verification gate:** `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
