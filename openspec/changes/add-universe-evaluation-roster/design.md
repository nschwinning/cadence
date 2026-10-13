## Context

See proposal.md — Why. The universe-evaluation agent is tool-less and
structured-output; its prompt is built deterministically by
`build_universe_evaluation_prompt(summary: UniverseSummary)` in
`backend/src/cadence/assets/universe_agent.py` from a compact `UniverseSummary`
frozen dataclass. `UniverseSummary` is produced by `_universe_summary(assets)`
in `backend/src/cadence/assets/service.py`, which already receives the full
`Asset` list as its argument — the roster can be built from that in-hand list
with no new query. Today `_universe_summary` keeps only aggregate counts
(`category_counts`, `sector_counts`, top-3 `top_concentrations`,
`unpriceable_listings`), so the prompt never names held tickers.

## Goals / Non-Goals

**Goals:**
- Give the agent the exact set of held tickers (grouped by sector) so it stops
  recommending additions that already exist.
- Keep prompt construction pure and deterministic so the existing prompt unit
  tests pattern continues to apply.

**Non-Goals:**
- No per-asset market-cap / liquidity / quality figures in the prompt (operator
  chose the sector-grouped roster option over the market-cap/liquidity option).
- No change to the agent's tools, structured `UniverseEvaluationOutput`, model,
  timeout, caching/fingerprint, persistence, API, or the frontend panel.
- No migration, schema, or change to *when* evaluation runs.
- No change to the supported scope (stocks + crypto only; no ETF/fixed-income).

## Decisions

**Roster shape on `UniverseSummary`.** Add one new field —
`sector_roster: tuple[tuple[str, tuple[RosterEntry, ...]], ...]` — an ordered
sequence of `(sector_label, entries)` groups, where each entry carries
`(ticker, name, is_eligible)`. A tuple-of-tuples (not a dict) keeps the frozen
dataclass hashable and pins ordering deterministically. `RosterEntry` may be a
small frozen dataclass or a `NamedTuple`; implementer's choice, kept local to
`universe_agent.py` alongside `UniverseSummary`.

- *Alternative considered:* an ordered `dict[str, list[...]]`. Rejected —
  mutable members undermine the frozen/hashable dataclass and make equality in
  tests fuzzier than tuples.

**Ordering.** Sector groups ordered by descending holding count, then sector
label ascending for ties (mirrors the existing `top_concentrations` tiebreak).
Within a group, tickers sorted ascending. Fully deterministic for testing.

**Crypto grouping.** Crypto is grouped under its own heading rather than mixed
into equity sectors. Crypto assets typically have no equity `sector`; group them
by category so the agent sees them as a distinct block. Implementation can use a
dedicated `"Crypto"` label for `category == CRYPTO` assets and fall back to the
asset's `sector` for equities.

**No-sector equities.** Equities with no `sector` are grouped under a stable
`"Unsectored"` heading (today `_universe_summary` already maps a missing sector
to `"none"` for `sector_counts`; the roster uses a human-readable `"Unsectored"`
label for the prompt while leaving the existing `sector_counts` behavior
untouched).

**Ineligible flag.** Ineligible holdings are flagged inline in the rendered
line (e.g. a trailing `[INELIGIBLE]` marker) so the agent can see which existing
names are not currently tradable without needing separate data.

**Prompt rendering.** `build_universe_evaluation_prompt` gains an "Assets already
in the universe (grouped by sector)" block rendered from `sector_roster`
(`Sector (count):` heading, then `  TICKER — Name` lines, ineligible flagged),
plus one explicit instruction: suggested additions must name only tickers NOT in
that roster. `_AGENT_INSTRUCTIONS` gets a matching reinforcing sentence.

## Risks / Trade-offs

- [Prompt token growth] → For ~120 assets the roster is ~1–2K tokens, acceptable
  for a once-per-change evaluation reusing the existing timeout. No pagination or
  truncation needed at current universe sizes.
- [Agent still free-forms suggestions] → The structured output does not mechanically
  enforce "not already present"; it is instructed, not validated. Acceptable —
  the explicit roster + instruction is the agreed fix, and post-hoc filtering is
  out of scope. Can be revisited if the agent still duplicates.
