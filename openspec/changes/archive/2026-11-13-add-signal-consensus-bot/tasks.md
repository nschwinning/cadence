## 1. Strategy

- [x] 1.1 Create `strategy_bots/signal_consensus.py` (`SignalConsensusParams`, `SignalConsensusStrategy`, `votes` helper); wire `StrategyKey.SIGNAL_CONSENSUS` ("Multi-Signal Consensus"), explanation, registry; verify with pytest (each vote's +1 / −1 / 0 on crafted windows; RSI votes with its own 15 closes; score ≥ consensus → enter, below → hold; overbought votes subtract; holding → hold; flat window; insufficient history; never short; params validation).
- [x] 1.2 Add the `signal_consensus_algo43` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: consensus fields, validation and payload; verify with vitest (preset fills and submits the params; consensus 9 blocks submit).
- [x] 2.2 `consensusChart.ts` registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Multi-Signal Consensus shipped; course deviations noted.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-signal-consensus-bot --strict` passes.
