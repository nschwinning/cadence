"""Constants and phase definitions for the asset-recommendations capability."""

from __future__ import annotations

from enum import StrEnum


class RunPhase(StrEnum):
    """Coarse lifecycle phase of a recommendation run.

    ``QUEUED`` → ``SEARCHING`` (agent working) → ``VALIDATING`` (checking and
    adding candidates) → terminal ``COMPLETED`` / ``FAILED``.
    """

    QUEUED = "queued"
    SEARCHING = "searching"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


#: Phases from which no further progress is made.
TERMINAL_PHASES = frozenset({RunPhase.COMPLETED, RunPhase.FAILED})


class CandidateOutcome(StrEnum):
    """Per-candidate result recorded in a run's ``results`` breakdown."""

    ADDED = "added"
    SKIPPED_DUPLICATE = "skipped-duplicate"
    SKIPPED_INELIGIBLE = "skipped-ineligible"
    ERROR = "error"


#: Multiplier applied to the requested count when asking the agent for
#: candidates, so that dedup/eligibility filtering still has enough to reach the
#: target. The requested count remains a hard upper bound on assets added.
CANDIDATE_OVERFETCH_FACTOR = 3

#: Floor on how many candidates the agent is asked to return, regardless of the
#: requested count, to give small requests room after filtering.
MIN_CANDIDATES_REQUESTED = 5
