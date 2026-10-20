## Features

- Make a new prompt version that uses fundamentals
- Make enroll in daily rebalancing obligatory (Cadence name is selected because of that) Do not make any trading decisions at build time. Let build portfolio just create the empty shell and then the first rebalancing job picks it up and makes the trading decision. Therefore newly built portfolios must be included in the first rebalancing job again.
- Make the ai model a parameter to select at portfolio build time to compare different models
- Use LiteLLM plus Dashboard to show token usage and costs
- Make watchlist assets opt in option at portfolio creation
- Show Portfolio Age on Paper Trading Page
- Merge Portfolios and Paper Trading Page into one since there is a 1:1 mapping anyway
- Use exisiting rclone cron job to dump the database to pcloud (how?)
- Add functionality to dynamicaly add indicator based trading bots (without AI), has to be like a rule engine, shall use the same universe and portfolio logic but it is a separate functionality from the ai trading, needs huge redesign and exploration first.

## Refactoring

- Make the Dashboard chart also use Apache ECharts and have the same look as the others and also add benchmark lines there (for all benchmark indexes)
- Redesign the Recent activity tile in the dashboard so that columns have the same size and move automation plus Recent activity to the bottom of the page
- Reformat the dates in the charts to use German date dd.MM
- Make the checkboxes in the portfolio creation mask two columns, let a designer agent do the design.

## Bugs

- On the same day (17.10.2026) I get pushover notifications for different portfolios that MSFT is the worst performer in one portfolio with -1.09% and the best performer with +2.08% on the other. How can that be?