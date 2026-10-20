## 1. Roster on the universe summary

- [x] 1.1 Add a `RosterEntry` type (frozen dataclass or `NamedTuple` with
  `ticker`, `name`, `is_eligible`) and a `sector_roster` field to `UniverseSummary`
  in `backend/src/cadence/assets/universe_agent.py` (ordered tuple of
  `(sector_label, entries)` groups); verify `mypy src/cadence` passes.
- [x] 1.2 Build `sector_roster` in `_universe_summary` in
  `backend/src/cadence/assets/service.py` from the already-in-hand `assets` list:
  group crypto under a `"Crypto"` heading, equities by `sector` (missing →
  `"Unsectored"`); order groups by descending count then label; sort tickers
  ascending within a group; carry the ineligible flag. Verify a new unit test
  asserts grouping, ordering, ineligible flag, crypto grouping, and the empty
  universe case.

## 2. Prompt rendering

- [x] 2.1 Render an "Assets already in the universe (grouped by sector)" block in
  `build_universe_evaluation_prompt` from `sector_roster` (`Sector (count):`
  heading, `  TICKER — Name` lines, ineligible flagged inline), plus an explicit
  instruction that suggested additions must name only tickers NOT in the roster.
  Verify a unit test asserts the block, a known held ticker, and the instruction
  appear and that the builder is deterministic for a fixed summary.
- [x] 2.2 Add a matching reinforcing sentence to `_AGENT_INSTRUCTIONS` ("never
  suggest adding a ticker already in the provided roster"), keeping the existing
  scope guardrails intact; verify the instructions-content unit test covers it.

## 3. Test updates and verification

- [x] 3.1 Update any existing `_universe_summary` / `build_universe_evaluation_prompt`
  tests that construct `UniverseSummary` or assert on prompt text to account for
  the new field and roster block; verify the full suite passes.
- [x] 3.2 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`
  and confirm all gates are green.
