## Features

- Use LiteLLM plus Dashboard to show token usage and costs
- Show Portfolio Age on Paper Trading Page
- Use exisiting rclone cron job to dump the database to pcloud (how?)
- Add functionality to dynamicaly add indicator based trading bots (without AI), has to be like a rule engine, shall use the same universe and portfolio logic but it is a separate functionality from the ai trading, needs huge redesign and exploration first.

## Refactoring

- Update the PnL columns in dashboard and portfolio page, they should always show the current portfolio value, the realized and unrealized pnl and be consistent. Also the portfolio value shall be updated every 30 seconds so that we have a live view feeling.
- Show if technical indicators are used on the session details page

## Bugs
