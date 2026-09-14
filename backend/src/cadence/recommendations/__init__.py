"""AI asset-recommendations capability.

A recommendation run asks an AI agent (with web search) for candidate tickers,
validates each against Cadence's eligibility criteria and the current universe,
auto-adds the eligible new ones, and records the run for later inspection.
"""
