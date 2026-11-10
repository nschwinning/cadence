## 1. Stop metadata (model + migration + both stop paths)

- [x] 1.1 Add a `StopReason` enum (`DRAWDOWN_KILL_SWITCH = "drawdown_kill_switch"`, `MANUAL = "manual"`) to `strategy_bots/constants.py`. Verify: imported without error, values match the spec strings.
- [x] 1.2 Add nullable columns to `BotSession` in `strategy_bots/models.py`: `stop_reason: str | None`, `stopped_at: datetime | None`, `summary_narrative: str | None`, `summary_fingerprint: str | None`, `summary_model: str | None`, `summary_generated_at: datetime | None`. Verify: mypy clean.
- [x] 1.3 Generate the Alembic migration (`cd backend && uv run alembic revision --autogenerate -m "bot session stop metadata and cached summary"`), review the add/drop columns, and apply it against the 5435 test DB. Verify: `uv run alembic upgrade head` then `downgrade -1` then `upgrade head` round-trips cleanly; tear the test DB container down afterward.
- [x] 1.4 In `service.stop_bot_session`, set `stop_reason = StopReason.MANUAL.value` and `stopped_at = datetime.now(UTC)` when transitioning to stopped. Verify: unit test asserts both set after a manual stop.
- [x] 1.5 In the kill-switch block of `service._tick_session`, set `stop_reason = StopReason.DRAWDOWN_KILL_SWITCH.value` and `stopped_at = tick_now`. Verify: unit test forcing a drawdown breach asserts both set.

## 2. Richer best/worst round-trip (entry/exit detail)

- [x] 2.1 Extend `TradeExtreme` (dataclass, service.py ~117) with `quantity`, `entry_price`, `entry_at`, `exit_price`, `exit_at`. Verify: mypy clean.
- [x] 2.2 Update `bot_trade_extremes` to carry the entry trade's `created_at` in `open_basis` and populate the new fields from the paired buy/sell. Verify: unit test on a known buy→sell ledger asserts entry/exit price+time+qty on best and worst.
- [x] 2.3 Extend `TradeExtreme` schema in `api/schemas.py` and the TS `TradeExtreme` type (`frontend/src/types/api.ts`) with the new fields. Verify: `tsc --noEmit` clean; existing KPI round-trip test still passes.

## 3. Summary assembly service

- [x] 3.1 Add a helper returning the full list of closed round-trips (reuse/refactor the `bot_trade_extremes` walk) so trade count and win rate (share with positive realized P&L) can be computed. Verify: unit test on a mixed win/loss ledger asserts count + win rate.
- [x] 3.2 Add a `SessionSummaryStats` dataclass + `bot_session_summary_stats(session, bot)` assembling: final value & total return ($ and fraction) from `bot_session_kpis`; `peak_value`; max drawdown (reuse the snapshot max-drawdown helper); lifespan days (start → `stopped_at`); closed-trade count & win rate; best/worst trade (with entry/exit); benchmark excess. Verify: unit test asserts each field on a seeded stopped session; absent fields (no round-trip / no benchmark) reported as None.
- [x] 3.3 Add a `_summary_fingerprint(stats, stop_reason, stopped_at)` sha256 over stop-stable inputs (not live current value). Verify: unit test — same inputs → same hash; changed input → different hash.

## 4. AI summary agent (cached, lazy)

- [x] 4.1 Create `strategy_bots/summary_agent.py` mirroring `assets/universe_agent.py`: tool-less `build_agent`, Pydantic `BotSummaryOutput` (narrative markdown + optional headline), `BotSessionSummaryAgent` Protocol seam, a `build_prompt(stats, stop_reason)` renderer, run-once-under-timeout, typed-unavailable on timeout/SDK failure, and `get_bot_summary_model()`. Verify: prompt-builder unit test is deterministic and includes the key stats; a fake agent returns a canned output.
- [x] 4.2 Add a `get_bot_summary_agent()` dependency factory (real impl) overridable in tests, mirroring the universe-evaluation agent dependency. Verify: test override injects a fake with no network.
- [x] 4.3 Add `bot_session_summary(session, bot, agent)` in service.py: raise a typed `BotSummaryUnavailableError`/409 when not STOPPED; otherwise assemble stats, compute the fingerprint, return the cached narrative when the fingerprint matches, else generate + persist (`summary_narrative/_fingerprint/_model/_generated_at`); on agent failure return stats with narrative None and persist nothing. Verify: unit tests — cache hit skips the agent; fingerprint change regenerates; agent failure → narrative None, stats intact; active bot → 409/typed error with no agent call.

## 5. API endpoint + schemas

- [x] 5.1 Add a `BotSessionSummaryRead` schema in `api/schemas.py` (stop_reason, stopped_at, the stats block, narrative + generated_at/model). Verify: `model_validate` round-trips the dataclass via `from_attributes`.
- [x] 5.2 Add `GET /bots/sessions/{id}/summary` in `api/routers/bots.py` (thin: DI → service → model_validate → map 404 unknown / 409 active). Verify: API test — 200 for a stopped session with stats (+ narrative when the fake agent succeeds); 409 for an active session; 404 for an unknown id.
- [x] 5.3 Add the TS summary type + `api/bots.ts` client fn + TanStack Query hook (enabled only when the bot is stopped). Verify: `tsc --noEmit` clean.

## 6. Frontend session-summary panel

- [x] 6.1 Add a `SessionSummary` panel to the bot detail page rendered only when `status === 'stopped'`: a stop reason + date banner, the stats grid (reuse existing tile/formatting; best/worst tiles show entry→exit price+date+qty), and the AI narrative with a loading state while generating and a neutral placeholder when the narrative is absent. Reuse the shared `Panel`. Verify: vitest — panel hidden for an active bot; shown for a stopped bot with stats + reason banner; narrative loading and null-placeholder states; best/worst tiles render entry/exit.
- [x] 6.2 Ensure the active-bot detail view and existing KPI tiles are unchanged. Verify: existing bot-detail vitest suite still green.

## 7. Verification gates

- [x] 7.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 Postgres test DB per project setup). Verify: all green; then tear the test DB container down (Docker-cleanup rule).
- [x] 7.2 Frontend: `cd frontend && npx vitest run && npx tsc --noEmit`. Verify: all green.
- [x] 7.3 `openspec validate add-stopped-bot-summary --strict`. Verify: passes.
