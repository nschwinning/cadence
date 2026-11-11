## Why

A deployed orchestrator's bots show up on the dashboard as standalone bots: each is its own
leaderboard row and equity-curve series, and the orchestrator itself does not appear at all.
Besides being confusing, this miscounts money:
- the orchestrator's undeployed free capital is missing from every aggregate;
- value drops off the dashboard when a bot stops, even though its cash returned to the
  pool;
- capital the orchestrator recycles into a new bot is counted as a fresh contribution,
  skewing the contribution-aware benchmark and excess return.

Separately, the same bot is named three different ways: `donchian_breakout · MSFT` on
the Bots page, "Turtle Breakout (Algo 25)" on the orchestrator page, and "Donchian Range
Breakout · MSFT" in pushes. That made one bot look like two.

## What Changes

- **Orchestrators become dashboard rows.** Each active orchestrator is one performance row
  of a new kind, `orchestrator`. It covers its free capital and all its bots, with the
  capital pool as its single contribution, its daily snapshots as the value series, and
  realised P&L and fees summed over its bots. Its bots are no longer rows of their own.
  The leaderboard, combined equity curve and overview tiles therefore count orchestrator
  money exactly once.
- **Dashboard UI:**
  - a third kind badge ("Orchestrator") in the leaderboard and the equity-curve selection;
  - orchestrator rows link to `/orchestrators/:id`.
- **Bots page:**
  - it still lists every bot;
  - orchestrator-deployed bots get a marker naming their orchestrator, linking to it.
- **One display name per bot, everywhere.** It is the label if set; otherwise the preset
  display name (or the strategy display name), then the traded set:
  - for example "Turtle Breakout (Algo 25) · MSFT";
  - used on the Bots list, the bot detail header, the orchestrator's bot table, the
    dashboard row, and push titles and lines;
  - it is exposed as `display_name` on bot reads, so the frontend does not re-derive it.
- No migration: everything is computed from existing tables (orchestrator snapshots
  already exist).

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `dashboard`: the overview aggregates orchestrators instead of their bots; per-session
  rows gain the orchestrator kind and its value and contribution basis.
- `bot-orchestrator`: adds "Orchestrator on the dashboard".
- `strategy-bots`: adds "Bot display name"; the dashboard adapter excludes orchestrator
  bots.
- `app-shell`:
  - adds "Orchestrator bots on the Bots list";
  - the combined equity curve and the leaderboard gain the orchestrator kind.

## Impact

- **Backend**:
  - new `bot_orchestrator/dashboard.py` (orchestrator rows);
  - `dashboard/service.py` (union; the `kind` literal gains `orchestrator`);
  - `strategy_bots/service.py`: exclude orchestrator bots from the adapter; a public
    `bot_display_name` replacing `_bot_label`;
  - `bot_orchestrator/runs.py` and `daily.py` (use the display name);
  - `api/schemas.py`: the `kind` literal; `display_name` on `BotSessionRead` and
    `OrchestratorBotRead`;
  - `api/routers/bots.py` and `bot_orchestrators.py`.
- **Frontend**:
  - `types/api.ts`;
  - `KindBadge.tsx`;
  - `PortfolioLeaderboard.tsx` (link);
  - `CombinedEquityChart.tsx` (badge only);
  - `BotsPage.tsx` and `BotSessionPage.tsx` (display name, orchestrator marker);
  - `OrchestratorDetailPage.tsx` (display name).
- **Unchanged**:
  - AI-session rows;
  - manual-bot rows (apart from their name);
  - the AI cost panel, which already lists orchestrators;
  - the recent-activity feed;
  - valuation of bots themselves.
