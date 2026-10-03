## 1. Cron schedule default

- [x] 1.1 In `docker-compose.yml`, change the cron sidecar default for `SNAPSHOT_SCHEDULE` from `15 16 * * 1-5` to `15 16 * * *` (16:15 ET, all 7 days). Verify the `${SNAPSHOT_SCHEDULE:-...}` override form is preserved so operator-pinned values still win.

## 2. Deployment docs

- [x] 2.1 In `.env.example`, change the `SNAPSHOT_SCHEDULE` example from `15 16 * * 1-5` to `15 16 * * *` so the documented default matches the compose default.
- [x] 2.2 In `README.md`, document that the end-of-day snapshot + daily P&L report runs every day including weekends (mirroring the existing weekend crypto-rebalance note), noting weekends capture crypto moves.

## 3. Verification

- [x] 3.1 Confirm no backend code change is needed: `snapshot_all_sessions` (`ai_portfolio/service.py`) and `/ai-portfolio/snapshot-daily` have no market-open guard or weekday assumption and are idempotent per calendar day — re-read the code to confirm, no edits.
- [x] 3.2 Run `openspec validate add-weekend-pnl-reports --strict` — passes.
- [x] 3.3 Sanity-check the compose cron wiring is unchanged except the default value (the `echo "$${SNAPSHOT_SCHEDULE} /usr/local/bin/snapshot.sh"` crontab line still references the same script).
