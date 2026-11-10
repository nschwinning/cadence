"""Domain errors for the bot orchestrator. The router maps each to an HTTP status."""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for every bot-orchestrator domain error."""


class OrchestratorNotFoundError(OrchestratorError):
    """No orchestrator with the requested id exists (404)."""


class OrchestratorRunNotFoundError(OrchestratorError):
    """No decision run with the requested id exists (404)."""


class InvalidOrchestratorConfigError(OrchestratorError):
    """The orchestrator configuration is invalid (422)."""


class OrchestratorNotActiveError(OrchestratorError):
    """The operation needs an active orchestrator (409)."""


class OrchestratorNotArchivableError(OrchestratorError):
    """Only a stopped orchestrator can be archived (409)."""


class OrchestratorRunInProgressError(OrchestratorError):
    """The orchestrator already has a run queued or running (409)."""


class OrchestratorUnavailableError(OrchestratorError):
    """The AI decision could not be produced (timeout or SDK failure).

    The run fails with this message and changes nothing; the next trigger retries.
    """
