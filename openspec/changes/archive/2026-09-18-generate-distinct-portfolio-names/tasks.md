## 1. Backend: name generator utility

- [x] 1.1 Add `src/cadence/utils/__init__.py` (if absent) and `src/cadence/utils/name_generator.py` porting `generate_unique_name(risk_profile, existing_names, max_attempts)` from trading-bot: adjective + famous-name word lists, retry against `existing_names`, numeric-suffix fallback.
- [x] 1.2 Unit tests for the generator: name format (with and without risk profile), uniqueness against a provided set, and the suffix fallback when the space is exhausted (seed the RNG for determinism).

## 2. Backend: use generated name at build time

- [x] 2.1 Add `portfolios_service.list_portfolio_names(session) -> set[str]` returning existing portfolio names.
- [x] 2.2 In `ai_portfolio/service.py`, replace `name=result.portfolio_name` in the build's `create_portfolio(...)` call with `generate_unique_name(risk_profile=params.risk_profile, existing_names=list_portfolio_names(session))`; keep `description=result.overall_thesis[:500]`.
- [x] 2.3 Update/extend build service tests to assert the created portfolio's name is generated (distinct from `result.portfolio_name`) and unique against a seeded existing name.

## 3. Backend: expose portfolio name on the session read model

- [x] 3.1 In `paper_trading/models.py`, add a `TYPE_CHECKING` import of `Portfolio` and a view-only, eager-loaded `portfolio` relationship (`relationship("Portfolio", lazy="joined", viewonly=True)`) on `PaperTradingSession`.
- [x] 3.2 Add a `portfolio_name` property on `PaperTradingSession` returning `self.portfolio.name` when resolvable, else `None`.
- [x] 3.3 In `api/schemas.py`, add `portfolio_name: str | None` to `PaperTradingSessionRead`.
- [x] 3.4 In `tests/test_paper_trading_api.py`, assert list and single-session reads include `portfolio_name`; add a case where the portfolio name is unresolved and `portfolio_name` is `null`.

## 4. Frontend: label sessions by portfolio name

- [x] 4.1 In `types/api.ts`, add `portfolio_name: string | null` to `PaperTradingSession`.
- [x] 4.2 In `pages/paper-trading/PaperTradingPage.tsx`, make the row's primary linked label the portfolio name (fallback to `strategy_key` when null/empty), show the strategy as secondary context, and rename the column header "Strategy" → "Portfolio".
- [x] 4.3 In `pages/paper-trading/PaperTradingSessionPage.tsx`, make the header title the portfolio name (fallback to `strategy_key`), with the strategy shown as secondary context.
- [x] 4.4 Update `PaperTradingPage.test.tsx` and `PaperTradingSessionPage.test.tsx`: primary label is the portfolio name, strategy is secondary, and a null-`portfolio_name` case falls back to the strategy.

## 5. Verification

- [x] 5.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 5.2 Frontend: `npm run typecheck && npx vitest run && npm run build`.
- [x] 5.3 Confirm no Alembic migration was introduced (`uv run alembic check` shows no drift).
