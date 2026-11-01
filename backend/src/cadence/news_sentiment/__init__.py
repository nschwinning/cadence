"""News-sentiment signal for the AI paper-trading stack.

A FinBERT-lineage tone signal classifying each asset's recent headlines into
positive / neutral / negative, served out-of-process via a sentiment sidecar
reached behind the ``SentimentScorer`` protocol and sourced from the Alpaca News
API behind the ``NewsSource`` protocol. The rebalance flow resolves a per-ticker
recency-weighted tone aggregate (cached in process by ``(ticker, date)``) and
attaches it to the agent's candidates and holdings, degrading to an explicit
"unavailable" marker rather than ever fabricating a signal or failing a run.
"""
