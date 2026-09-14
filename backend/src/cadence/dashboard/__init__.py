"""Dashboard capability: live, read-only aggregation over existing domains.

Computes an at-a-glance overview of the app — asset-universe size and
composition, portfolio count, and paper-trading activity — with cheap aggregate
queries over the current rows. No new tables and no background job: the numbers
are computed on each request by reusing the existing domain service functions.
"""
