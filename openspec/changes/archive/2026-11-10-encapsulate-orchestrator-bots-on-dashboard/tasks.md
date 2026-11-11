## 1. Bot display name (backend)

- [x] 1.1 Add `bot_display_name(bot)` to `strategy_bots/service.py` (label → preset display name → strategy display name, then ` · ` + traded set), replace every `_bot_label` use, and use it for the bot dashboard row label. Verify: unit tests — labelled bot, unlabelled preset bot ("Turtle Breakout (Algo 25) · MSFT"), unlabelled custom bot ("Donchian Range Breakout · MSFT"), multi-symbol bot ("… · 3 symbols"); kill-switch and daily push titles use it.
- [x] 1.2 Expose `display_name` on `BotSessionRead` (set in the bots router's `_to_read`) and `OrchestratorBotRead`; switch the orchestrator's run-summary and daily-push bot names to `bot_display_name`. Verify: API tests — bot reads and orchestrator detail bots carry the display name; existing orchestrator notification tests updated to the new wording and passing.

## 2. Dashboard encapsulation (backend)

- [x] 2.1 Exclude bots with `orchestrator_id` from `strategy_bots.dashboard_performances`; widen the `kind` literal to include `"orchestrator"` in `SessionPerformance` and the API schema. Verify: unit test — with one manual bot and one orchestrator bot, only the manual bot is returned.
- [x] 2.2 New `bot_orchestrator/dashboard.py` building one `SessionPerformance(kind="orchestrator")` per active orchestrator (value, snapshot series / pre-snapshot point, single pool contribution, range P&L baseline, realised/fees summed over all its bots, unrealised over unreturned bots, benchmark value), and union it into `get_dashboard_overview`. Verify: service tests — the $10,000 pool / $6,700 free / bot worth $3,350 case gives value $10,050 and one $10,000 contribution; recycled capital (stop + redeploy) still one contribution; the series windows to the range and falls back to one live point without snapshots; range P&L uses the range-start snapshot; stopped orchestrators produce no row; overview API test shows the orchestrator row and no row for its bot.

## 3. Frontend

- [x] 3.1 Types (`kind` union, `display_name` on `BotSession` and `OrchestratorBot`), `KindBadge` orchestrator style, and leaderboard link by kind. Verify: vitest — an orchestrator row is badged "Orchestrator" and links to `/orchestrators/<id>` in the leaderboard; the equity-chart selection shows the orchestrator badge; `npx tsc -p tsconfig.app.json --noEmit` reports no new errors.
- [x] 3.2 Bots page and bot detail use `display_name`, show the strategy display name instead of the raw key, and render the orchestrator marker linking to the orchestrator; the orchestrator bot table uses `display_name`. Verify: vitest — an orchestrator bot row shows "Turtle Breakout (Algo 25) · MSFT" and an "Orchestrator · First Orchestrator" link; a manual bot shows no marker; the detail header shows the display name; existing Bots/detail/orchestrator tests updated and passing.

## 4. Verification gates

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 test DB. Verify: all green; tear the Cadence DB container down.
- [x] 4.2 Frontend: `cd frontend && npx vitest run && npx tsc -p tsconfig.app.json --noEmit`. Verify: vitest green; no type errors beyond the three known pre-existing axios-mock errors.
- [x] 4.3 `openspec validate encapsulate-orchestrator-bots-on-dashboard --strict`. Verify: passes.
