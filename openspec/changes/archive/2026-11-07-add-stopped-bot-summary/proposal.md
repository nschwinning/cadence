## Why

When a strategy bot stops — whether the drawdown kill-switch fired or the user stopped it manually — the detail page still shows the same live-oriented KPI tiles as an active bot, with no retrospective "how did this session go" view. A stopped session is a finished story: the user wants a concise wrap-up (headline stats plus a plain-language narrative) that explains the outcome. Today the app does not even record *why* or *when* a bot stopped, so that story cannot be told accurately.

## What Changes

- Record stop metadata on every stop: new `bot_sessions.stop_reason` (`drawdown_kill_switch` | `manual`) and `stopped_at` timestamp, set in both the kill-switch path (`service._tick_session`) and the manual-stop path (`service.stop_bot_session`). Nullable for pre-existing stopped rows (no backfill).
- Add a **Session summary** section to the bot detail page that renders **only when the bot is STOPPED**. It shows:
  - a stop banner (reason + date),
  - a curated stats block: final value & total return ($/%), peak value & max drawdown, lifespan (days) & round-trip trade count & win rate, best/worst trade & benchmark excess return,
  - a cached, AI-generated narrative summary of how the session went.
- Extend the best/worst round-trip trade data to carry the **exact entry and exit** (entry price + date, exit price + date, quantity), not just net P&L + ticker.
- Generate the AI narrative **lazily on first view** of a stopped bot and **persist it with an input fingerprint**, mirroring the existing universe-evaluation cached-AI pattern: regenerate only when the summarized inputs change; degrade gracefully to no narrative if the agent fails.
- Add a read endpoint that returns the summary payload (stats + reason + stopped_at + AI narrative) for a stopped bot, and is empty/unavailable for an active bot.

No change to valuation, the tick loop, or the kill-switch *threshold* logic — only the recording of reason + timestamp. AI-portfolio sessions are unaffected (strategy bots only).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: add a new **Stopped-session summary** requirement (summary section, stats, cached AI narrative, stopped-only visibility); modify the lifecycle requirements to record **stop reason + stopped_at** on both stop paths; modify the best/worst-trade KPI requirement to carry **exact entry/exit detail**.

## Impact

- **DB / migration**: new Alembic migration adding `stop_reason`, `stopped_at`, and the cached-summary columns (text + fingerprint + generated-at) to `bot_sessions`. First strategy-bots change needing a migration (prior ones used free-text `strategy_key`).
- **Backend**: `strategy_bots/models.py` (new columns); `strategy_bots/service.py` (`stop_bot_session`, `_tick_session` kill-switch block, `bot_trade_extremes` + `TradeExtreme`, new summary-assembly + lazy-cache function, max-drawdown/benchmark/KPI reuse); new AI agent module mirroring `assets/universe_agent.py`; `api/schemas.py` (`TradeExtreme`, new summary schema); `api/routers/bots.py` (new summary GET).
- **Frontend**: bot detail page gains a stopped-only **Session summary** panel (stats grid, reason banner, AI narrative with loading + null-placeholder states; best/worst trade tiles show entry/exit); `types/api.ts` + `api/bots.ts` extended for the summary payload and the richer trade extremes.
- **AI usage**: one summarization call per stopped bot (cached); respects the existing agent model/timeout config conventions.
