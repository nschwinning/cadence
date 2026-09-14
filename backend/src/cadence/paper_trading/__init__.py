"""Paper-trading persistence capability.

Stores the results of the AI portfolio / rebalancing flow: paper-trading
sessions and their trades, run history, and closed positions. Ported from
trading-bot's ``paper_trading_repository`` and expressed in Cadence's ORM +
service conventions. Writes happen via the ai_portfolio flow (built later); the
router here is read-only.
"""
