"""AI-managed portfolio capability.

Ports trading-bot's AI portfolio *build* and daily *rebalance* flows into
Cadence's layered conventions: a structured-output agent (:mod:`agent`), a
broker-only executor (:mod:`executor`), an ORM audit trail (:mod:`models`),
service orchestration (:mod:`service`), and a single-worker job runner
(:mod:`background`). Persistence reuses the portfolios and paper-trading domains.
"""
