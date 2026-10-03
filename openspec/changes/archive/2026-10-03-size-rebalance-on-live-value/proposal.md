## Why

When an AI paper-trading session rebalances, the executor sizes every target weight
against the session's **original frozen allocated capital**
(`AIPortfolioExecutor(broker, session_row.allocated_capital)` →
`base_capital = self.allocated_capital`). Because the target weights sum to ~1, the run
only ever deploys capital up to the *original* allocation — never the session's actual
current equity.

The consequence is a persistent drift: once a session has **gains**, the profit is never
redeployed. A session that grew from $10,000 to $12,000 still has its weights applied to
$10,000, leaving ~$2,000 permanently idle as uninvested cash (and compounding as more
gains accrue). Symmetrically, after losses the run keeps targeting the original $10,000,
over-committing relative to the session's shrunken equity. The session's reported value
is correct, but the rebalance never rebalances to the money the session actually has.

This is wrong: a rebalance should allocate the portfolio's **current** value across its
target weights, so realised and unrealised gains are put back to work (and losses are
respected) each run.

## What Changes

- **Automated rebalances size target weights against the session's current
  marked-to-market value** (allocated capital + realised P&L − fees + unrealised P&L =
  current positions' market value + free cash), instead of the frozen allocated capital.
  The target-weight delta model and all guardrail enforcement are unchanged — only the
  base capital the weights are applied to changes.
- **The initial build is unchanged.** At build time the session's current value equals
  its allocated capital (no positions, no P&L), so build sizing continues to use the
  allocated capital with identical results. Only the rebalance seam changes.
- No change to how performance/KPIs/valuation are computed (those already use current
  value), to the order model, to notifications, or to scheduling.

## Capabilities

### New Capabilities

_None._ This change extends an existing capability.

### Modified Capabilities

- `ai-paper-trading`: add a requirement that an automated rebalance sizes its target
  weights against the session's current marked-to-market value rather than the frozen
  allocated capital, so gains are redeployed and losses respected, while the build
  continues to size against the allocated capital.

## Impact

- **Backend**: `ai_portfolio/service.py` — at the rebalance seam (~855) construct the
  executor's base capital from `paper_trading.service.compute_session_value().total_value`
  instead of `session_row.allocated_capital`; `ai_portfolio/executor.py` — the
  rebalance base capital becomes a per-run input (the `execute_rebalance` sizing base),
  leaving the build path (`execute_build`) sizing off the allocated capital as today.
- **No DB migration** — pure runtime sizing change; nothing persisted changes.
- **Frontend**: none.
- **Cross-change note**: the not-yet-applied `add-weekend-crypto-rebalance` recorded (its
  D5) that "weekday execution still sizes off allocated_capital." This change supersedes
  that statement for the weekday full-portfolio run (base becomes current value); the two
  remain consistent — crypto-only runs there size against the crypto investable budget,
  which is itself derived from current value. See design.md.
