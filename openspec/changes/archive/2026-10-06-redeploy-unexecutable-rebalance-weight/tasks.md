## 1. Executor: redeploy unexecutable target weight

- [x] 1.1 In `execute_rebalance` (`ai_portfolio/executor.py`), add a step that classifies each normalized target as executable (priceable + can fund the minimum tradable amount against `net_base`) or unexecutable, reusing the quote fetch and the whole-share / min-notional affordability tests already in the loop/planners. Verify with a unit test asserting the classification for a priceable-affordable, an unpriceable, and a too-small target.
- [x] 1.2 Redistribute unexecutable targets' weight proportionally across the executable targets as a bounded fixed-point loop (re-normalize among the executable set, re-check executability, stop when the set is stable, deployable cash above the buffer is exhausted, or the iteration cap is hit) per design D1. Verify with a unit test: a rebalance with one 15%-weight unpriceable target deploys that weight into the remaining targets (invested fraction rises, residual cash ≈ reserved buffer).
- [x] 1.3 Ensure redeployment never deploys below the reserved cash buffer (design D1). Verify with a unit test asserting post-rebalance deployable cash is not driven below the buffer.
- [x] 1.4 When `caps` is provided, apply the guardrail clamp to the redistributed weight vector so redeployed weight still satisfies per-asset / per-asset-class / max-invested caps, with un-placeable weight remaining cash. Verify with a unit test on a guardrails-enabled session that redeployment respects the caps.
- [x] 1.5 Preserve the existing delta model, crypto-only scoping (redeploy only within the crypto-scoped target set), `market_open` equity-skip, and sells-before-buys phasing. Verify existing executor tests still pass and add a crypto-only redeployment test.
- [x] 1.6 Handle the all-unexecutable case: leave capital as cash and complete without error, recording each target as not executed. Verify with a unit test where no target can be priced.

## 2. Executor: record unexecutable targets explicitly

- [x] 2.1 Change the rebalance planning so a target skipped for affordability ("too small for one share" / sub-min-notional for a wanted position) is recorded as `TradeResult(executed=False, reason=...)` instead of a silent `None`, while a legitimate `|delta| < 1` adjustment of an already-at-target holding remains a non-surfaced no-op (design D3). Verify with a unit test asserting the too-small target appears in results with the expected reason and the at-target no-op does not.
- [x] 2.2 Confirm the unpriceable-target reason is still recorded (regression). Verify via the existing/added test asserting the "No price available" result is present.

## 3. Service: exclude known-unexecutable tickers from rebalance candidates

- [x] 3.1 In the rebalance candidate assembly (`ai_portfolio/service.py`), filter out tickers known to be unexecutable on the configured brokerage before handing candidates to the agent (design D4), resolving the Open Question from how the universe is currently assembled. Verify with a service test that a known-unexecutable ticker is omitted from the agent's candidates.
- [x] 3.2 Ensure the exclusion does not prevent selling/exiting an already-held, now-unexecutable position. Verify with a service/executor test that a held excluded ticker can still be exited.

## 4. Regression and integration

- [x] 4.1 Verify the "skip a rebalance that can only buy with no deployable cash" behavior is unchanged with redeployment in place (regression test).
- [x] 4.2 Confirm no DB migration, no `api/schemas.py` read-model change, and no frontend change are required (design D5); if any surfaces, stop and update the proposal/design before proceeding.
- [x] 4.3 Run the full backend gate: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green.

## 5. Spec validation

- [x] 5.1 Run `openspec validate redeploy-unexecutable-rebalance-weight --strict` and resolve any issues.
