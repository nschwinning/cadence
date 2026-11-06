## Context

See proposal.md — Why. The market clock already exists on the broker (`Broker.is_market_open() -> bool`, implemented by `AlpacaBroker` via `/v2/clock` and by `StubBroker` returning `True`) but is never surfaced to the frontend. The dashboard overview service (`get_dashboard_overview(db, range_, broker)`) already receives the broker, and the overview router already injects `BrokerDep`, so the seam to expose market state exists end-to-end with no new wiring. The paper-trading valuation layer already consults the same clock via `_market_is_open`, which wraps the call and defaults to open on any failure.

## Goals / Non-Goals

**Goals:**
- Expose a single boolean `market_open` on the existing overview payload.
- Keep the dashboard from ever failing because the clock call failed.
- Render an honest open/closed label consistent with the existing header indicator pattern.

**Non-Goals:**
- No new clock/market endpoint — a field on the existing overview suffices.
- No change to valuation (`compute_session_value`, EOD-vs-live gating, crypto-live pricing, strategy-bot valuation), total-value aggregation, or the 30s refetch cadence.
- The badge does not represent crypto's 24/7 market; it reflects only the US equity clock.

## Decisions

- **Field on the overview, not a new endpoint.** The overview already carries the broker and is already polled every 30s; adding `market_open` reuses that fetch and keeps the badge in lockstep with the value it contextualizes. A separate `/clock` endpoint would mean a second request and a second cadence to reconcile. Rejected.
- **Safe default = open, mirroring `_market_is_open`.** Wrap `broker.is_market_open()` so any exception falls back to `True`. Chosen over default-closed so the badge never contradicts the valuation layer (which prices equities live on clock failure): if the clock is down and values are still moving, claiming "closed" would be the misleading outcome. The fallback is documented in the spec and surfaced in design so the badge wording stays honest.
- **Reuse the `HealthIndicator` dot+label `role="status"` pattern.** The new badge sits in the same header row (top-right, beside `HealthIndicator`) with a green dot for open and a neutral/grey dot for closed, so it reads as a peer status chip rather than a new UI idiom.
- **Boolean, not an enum/string.** Two states (open/closed) with a documented fallback need only a boolean; an enum would invite an "unknown" state the valuation layer does not itself distinguish.

## Risks / Trade-offs

- **Clock failure shows "open" when the market may actually be closed** → Accepted and documented: this matches the valuation layer's own behaviour, so the label stays consistent with the (live) numbers the user sees. Flipping the default would make the label disagree with the displayed values.
- **Per-overview-fetch clock call adds a broker round-trip every 30s** → `AlpacaBroker.is_market_open()` is a single lightweight `/v2/clock` GET and the stub is in-memory; the cost is negligible and already incurred by the valuation path during market hours.
- **Badge reflects equities only, not crypto** → Intentional and documented; the label's purpose is to explain the equity freeze, and crypto being always-live is the unexplained-looking part it clarifies.

## Open Questions

None.
