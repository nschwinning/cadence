## Why

The bot catalog now holds 19 strategies and 32 presets, and the orchestrator AI chooses among all
of them. Its briefing gives each preset only a name, the strategy's display name, a course
reference, a one-line description and risk values — it never sees what a strategy actually does,
and nothing tells it which presets are trend-following, breakout or mean-reversion, although its
instructions ask it to match exactly those families to market conditions. Less familiar presets
(VAMA, Volume Breakout, Bayesian Trend Predictor, …) are therefore hard for it to place.

Separately, the Orchestrators page gained a read-only preset catalog list as a direct edit; the
`bot-orchestrator` spec does not describe it yet.

## What Changes

- Every registered strategy declares a **style** — `trend`, `momentum`, `breakout`,
  `mean_reversion` or `regime_switching` — in the strategy constants; a test makes a future
  strategy without a style fail CI.
- The decision briefing gains a **Strategies** section: one entry per strategy used by a preset,
  with its key, display name, style and plain-language explanation (sent once per strategy, not
  per preset, to keep the prompt compact).
- Each **preset** entry gains its `strategy_key` and `style` (to join to the Strategies section)
  and its strategy parameters.
- The agent instructions refer to the styles when matching presets to conditions
  (trend / momentum / breakout for up-trends with healthy breadth, mean-reversion for
  pulled-back names in intact trends, regime-switching where the regime is unclear) and to the
  strategy explanations.
- The `bot-orchestrator` spec's **Orchestrator views** requirement documents the existing preset
  catalog list on the Orchestrators page (no code change).
- No migration, no API or frontend change, no new settings. The prompt grows by roughly
  2–3k tokens per run.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `bot-orchestrator`: the decision briefing carries strategy explanations and styles; the views
  requirement covers the preset catalog list.

## Impact

- Backend: `strategy_bots/constants.py` (`StrategyStyle`, `STRATEGY_STYLES`),
  `bot_orchestrator/briefing.py` (`strategy_rows`, richer `preset_rows`),
  `bot_orchestrator/agent.py` (Strategies prompt section, instruction wording).
- Tests: briefing and agent-prompt tests; a style-coverage test.
- Existing runs keep their stored briefings; only new runs carry the new sections.
