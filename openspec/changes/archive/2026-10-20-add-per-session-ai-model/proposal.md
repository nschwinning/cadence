## Why

Every AI paper-trading session currently runs on a single globally-configured model (`settings.AI_PORTFOLIO_MODEL`), so there is no way to compare how different models allocate and rebalance a portfolio, and no record of which model produced any given run. To evaluate models against each other, the operator needs to pick a model when building a portfolio, freeze it on the session, and see which model generated each AI run.

## What Changes

- Add a **fixed, server-defined model catalog** (mirroring the existing benchmark catalog): an `AIModel` enum + display-name map + a `GET /paper-trading/models` endpoint returning `{id, name}` entries.
- The AI build request accepts an optional `model` field typed as the catalog enum; an out-of-catalog id is rejected with **422** (same mechanism as `benchmark`). When omitted, the model resolves to the current configured default.
- The chosen model is **frozen on the session**: a new non-nullable `model` column on `paper_trading_sessions`, threaded through `AIBuildParams` → `create_session`. Existing rows are backfilled with `gpt-5-mini` via `server_default` — the model those sessions actually ran on — so their per-run attribution stays honest even though the *new* default for future builds becomes `gpt-6-luna`.
- The **configured default model changes to `gpt-6-luna`** (`config.py` `AI_PORTFOLIO_MODEL`), so a build that omits a model — and the build form's default — now uses `gpt-6-luna`. This is distinct from the migration backfill above, which preserves `gpt-5-mini` for pre-existing sessions.
- The rebalance agent (which drives **both** the opening allocation and daily rebalances) runs on the **session's frozen model** instead of the hardcoded global setting, falling back to the setting only if a session's value were somehow absent.
- Each AI run **records the model that produced it**: a new scalar `model` column on `ai_portfolio_events`, set when the run event is finalized, and surfaced in the run read.
- The session read exposes `model`; the build form gains a model dropdown; session-detail and run-detail each gain a read-only "Model" tile.

**Starter catalog (confirmed with the user, 2026-10-20).** The user asked to seed the catalog with a couple of small, fast, cheap models from the gpt-5.6 and gpt-6 series. Research (OpenAI API lineup, Oct 2026) shows those series dropped the "mini" name; the cheapest/fastest tier in each is **Luna**. Starter catalog:

  | id | display name | note |
  | --- | --- | --- |
  | `gpt-5-mini` | GPT-5 Mini | the model existing sessions ran on; kept in the catalog + used for the migration backfill |
  | `gpt-5.6-luna` | GPT-5.6 Luna | small/fast/cheap tier of the 5.6 series (~$0.20/$1.20 per 1M) |
  | `gpt-6-luna` | GPT-6 Luna | cheapest/fastest current model (~$0.10/$0.50 per 1M); **new configured default** |

  The configured default (`AI_PORTFOLIO_MODEL`) becomes `gpt-6-luna`. The catalog is easily extended later by adding enum members; this set is "enough to begin with" for model comparison.

## Capabilities

### New Capabilities
<!-- None. The model catalog is folded into ai-paper-trading, mirroring how the
     benchmark catalog lives within that capability rather than as a standalone one. -->

### Modified Capabilities
- `ai-paper-trading`: the build request accepts, validates (422 on unknown), persists, and freezes a catalog model on the session; the opening allocation and rebalances run on the session's frozen model; each AI run records its model; the session read exposes the model; a new model catalog is served.
- `app-shell`: the AI build form offers a model dropdown sourced from the catalog; the session-detail page shows the session's model; the run-detail page shows the model that produced the run.

## Impact

- **Backend**: `paper_trading/constants.py` (new `AIModel` enum + display map), `paper_trading/models.py` + new Alembic migration (session `model` column; down_revision `e8f3a1c5d2b4`), `ai_portfolio/models.py` + migration (event `model` column), `schemas.py` (`ModelCatalogEntry`, build request, session read, run read), `paper_trading.py`/`ai_portfolio.py` routers (catalog endpoint, default resolution), `ai_portfolio/params.py`, `ai_portfolio/flows/build.py` + `flows/rebalance.py`, `ai_portfolio/agent.py` + `_helpers.py`.
- **Frontend**: `types/api.ts`, `api/paperTrading.ts` (`listModels`/`useModels`), `BuildAIPortfolioCard.tsx` (dropdown), `PaperTradingSessionPage.tsx` + `RunDetailPage.tsx` (Model tiles).
- **Config**: `AI_PORTFOLIO_MODEL` remains the default source and its value changes from `gpt-5-mini` to `gpt-6-luna`, so new builds that omit a model use `gpt-6-luna`. The session-column migration still backfills *existing* rows with `gpt-5-mini` (what they ran on), independent of this new default.
- **Behavior change for new builds** (the default model shifts to `gpt-6-luna`); the API contract is unchanged (model stays optional on the request). Two additive migrations with non-null backfills; existing sessions keep running on `gpt-5-mini`.
