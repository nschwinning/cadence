## Context

- **How the overview is built.** `dashboard.service.get_dashboard_overview` builds AI rows,
  then lazily imports `strategy_bots.service.dashboard_performances`. That function adapts
  **every active bot** into a `SessionPerformance(kind="bot")`. The lazy import avoids a
  cycle: `strategy_bots` imports `SessionPerformance` from the dashboard.
- **What rows carry.** `SessionPerformance` holds the live value, range P&L,
  realised/unrealised P&L, fees, a windowed value series, contributions and a
  since-inception benchmark value. The client sums the rows into the tiles, equity curve
  and leaderboard.
- **What orchestrators already provide.** `service.orchestrator_figures` (live value =
  free capital + unreturned bots), daily `BotOrchestratorSnapshot` rows (value per date),
  and the capital pool (`orchestrator.capital`).
- **How bots are named today.** `bot.label || strategy_key · tickers` in two frontend
  helpers, `preset_name ?? …` on the orchestrator page, and `_bot_label` (strategy
  display name · traded set) for pushes.

## Goals / Non-Goals

**Goals:**
- Count orchestrator money exactly once on the dashboard, with no drop-off when bots stop
  and no phantom contributions when capital is recycled.
- One bot display name computed in one place (the backend).

**Non-Goals:**
- Intraday orchestrator value points (the series is daily, from snapshots; the live value
  covers intraday).
- Changing bot valuation, the AI cost panel, or the recent-activity feed.
- Hiding orchestrator bots from the Bots page.

## Decisions

**1. Filter in the bot adapter; add the orchestrator rows in the dashboard union.**
- `strategy_bots.dashboard_performances` skips bots with `orchestrator_id` set. It reads
  the existing column and needs no orchestrator import.
- The overview then lazily imports `bot_orchestrator.dashboard.dashboard_performances`
  and extends the rows, following the same lazy-import pattern as the bots.
- The `kind` literal becomes `"ai" | "bot" | "orchestrator"` in `SessionPerformance`,
  the API schema and the TS type.

**2. Orchestrator row figures** (`bot_orchestrator/dashboard.py`):
- **Current value:** `orchestrator_figures(...).value`, the same figure as the
  orchestrator page.
- **Value series:** orchestrator snapshots, windowed to the range. Before the first
  snapshot, a single point `(as_of, current value)` is used, mirroring the bot adapter's
  pre-snapshot anchor.
- **Contribution:** exactly one, `(first snapshot date or as_of, capital)`.
  `allocated_capital = capital`.
- **Range P&L:** `current − baseline`, where the baseline is the latest snapshot on or
  before the range start, or the capital pool for Max or when there is none (the bot
  adapter's rule).
- **Realised P&L, unrealised P&L and fees:** built by calling the existing
  `strategy_bots.dashboard_performance(bot, range_)` for every bot the orchestrator ever
  deployed, then:
  - realised P&L and fees summed over all of them, since a stopped bot's realised P&L
    in range still belongs to the orchestrator;
  - unrealised P&L summed over the unreturned ones.
  This reuses the bots' exact range semantics instead of re-deriving them.
- **Benchmark value:** `rebased_benchmark_value` over the single contribution in the
  orchestrator's benchmark, the same call the bot adapter makes.
- **Label:** the orchestrator's label; **id:** the orchestrator id.

**3. Bot display name in the backend only.**
- `strategy_bots.service.bot_display_name(bot)`: label, else the preset display name,
  else the strategy display name, then ` · ` and the traded set (one ticker, or
  "N symbols", reusing `_traded_set_label`).
- It replaces `_bot_label`, so kill-switch and daily push titles change from
  "Donchian Range Breakout · MSFT" to "Turtle Breakout (Algo 25) · MSFT" for preset bots.
- Exposed as `BotSessionRead.display_name` and `OrchestratorBotRead.display_name`. The
  bot dashboard row's `label` uses it too.
- The orchestrator's run summary and daily push lines (`_describe`, `_bot_name`) switch
  to it as well, so pushes and pages agree.
- Rejected: a frontend helper mirroring the rule. It would duplicate the preset catalog
  lookup and drift.

**4. Frontend.**
- **`KindBadge`** gains `orchestrator` (label "Orchestrator", its own colour).
- **Leaderboard link:** by kind (`ai` → session, `bot` → `/bots/:id`, `orchestrator` →
  `/orchestrators/:id`).
- **Equity-chart selection** needs no logic change; it renders `KindBadge`.
- **Bots page:**
  - rows show `display_name`;
  - an orchestrator marker ("Orchestrator · <label>" linking to `/orchestrators/<id>`) is
    rendered when `orchestrator_id` is set, using the `orchestrator_label` the read
    already carries.
- **Bot detail header** shows `display_name`; the strategy line under it shows the
  strategy's display name instead of the raw key.
- **Orchestrator bot table** shows `display_name`.

## Risks / Trade-offs

- [The orchestrator's equity series is daily and starts at its first 16:15 snapshot, so a
  new orchestrator's curve is one live point for the first day] → this matches how a new
  bot behaves today.
- [Building every bot's row to sum realised P&L and fees costs a few queries per
  orchestrator bot] → small counts (a handful of bots per orchestrator); the overview
  already does this work per bot today.
- [Push titles for existing preset bots change wording] → intended (consistency); it's
  only a title text change.
- [Before this change, dashboard history included orchestrator bots as bot rows] → no
  stored dashboard state exists; the rows are computed on read, so the dashboard simply
  shows the new grouping from deploy on.

## Migration Plan

No schema change. Deploy as usual; the dashboard regroups on the next load.
