## Features

- Use LiteLLM plus Dashboard to show token usage and costs
- Show Portfolio Age on Paper Trading Page
- [x] Use exisiting rclone cron job to dump the database to pcloud — `scripts/backup-cadence.sh` reuses the Pi's `pcloud:` remote (both DBs + config, atomic upload, 14-day retention); add a crontab entry at 02:15.
- Add functionality to dynamically add indicator based trading bots (without AI), has to be like a rule engine, shall use the same universe and portfolio logic but it is a separate functionality from the ai trading, needs huge redesign and exploration first.
- Add Authentication using e.g. KeyCloak

## Refactoring

- Show if technical indicators are used on the session details page

## Bugs
 you