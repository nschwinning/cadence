## Features

- [x] Use LiteLLM plus Dashboard to show token usage and costs — shipped: LiteLLM proxy layer plus a per-portfolio AI cost panel on the dashboard (`/dashboard/ai-costs`), backed by the LiteLLM spend-log DB.
- [x] Show Portfolio Age on Paper Trading Page — shipped: the portfolios table has an Age column (creation date on hover).
- [x] Use exisiting rclone cron job to dump the database to pcloud — `scripts/backup-cadence.sh` reuses the Pi's `pcloud:` remote (both DBs + config, atomic upload, 14-day retention); add a crontab entry at 02:15.
- Add functionality to dynamically add indicator based trading bots (without AI), has to be like a rule engine, shall use the same universe and portfolio logic but it is a separate functionality from the ai trading, needs huge redesign and exploration first.
- Add Authentication using e.g. KeyCloak

## Refactoring

- [x] Show if technical indicators are used on the session details page — already shipped: a "Technical indicators" fact tile is rendered on the session-detail page.
- Session comparison chart: distinct colours are guaranteed only up to the 8-colour palette; if more than 8 sessions are ever compared at once, extend `CATEGORICAL_PALETTE` (or generate evenly-spaced hues) so lines never repeat a colour.
- `colorForKey` in `lib/palette.ts` is now unused by any component (only its own unit test). Remove it (and its test) if we don't want the hash-collision footgun around.

## Bugs

- [x] Two portfolios' comparison-chart lines could share a colour on the Paper Trading page — `SessionComparisonChart` used `colorForKey(session_id)` (hash into 8 slots, collides by chance). Fixed: colours now assigned by list position (`categoricalColor(index)`), distinct until the palette is exhausted.
- [x] Not a bug (investigated): crons firing an hour earlier in CET during the ~1–3 week US/EU DST-mismatch windows is correct — jobs are anchored to the US market open/close (ET-pinned cron), so the European offset is what flexes.
