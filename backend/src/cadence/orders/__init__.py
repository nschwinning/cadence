"""Order journal: durable, idempotent recording of every broker order Cadence sends.

Every order goes through :class:`cadence.orders.gateway.OrderGateway`, which records the
intended order (with a unique client order id) in a commit of its own *before* the broker
sees it, refuses sells larger than the account holds, and records the broker's answer. The
owner books the fill and marks the journal row booked in its own transaction;
:mod:`cadence.orders.reconcile` books whatever an owner never got to.
"""
