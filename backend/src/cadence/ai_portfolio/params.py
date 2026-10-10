"""Build-job parameters for the AI-portfolio service.

:class:`AIBuildParams` is the frozen request payload persisted on a build event's
``request_payload`` and reconstructed from it. Kept in its own module so both the
build flow and the event-CRUD layer can depend on it without importing the flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cadence.assets.category import AssetScope
from cadence.config import settings


@dataclass(frozen=True)
class AIBuildParams:
    """Inputs for a build job, persisted on the event's ``request_payload``.

    The build allocates over the entire current asset universe (with bounded
    discovery), so no ticker list or per-asset/position caps are accepted.
    """

    allocated_capital: float = 10000.0
    risk_profile: str = "balanced"
    asset_types: str = AssetScope.BOTH.value
    daily_rebalancing: bool = False
    benchmark: str = settings.DEFAULT_BENCHMARK
    use_technical_indicators: bool = False
    stop_loss_enabled: bool = False
    stop_loss_pct: float | None = None
    risk_guardrails_enabled: bool = False
    max_allocation_pct: float | None = None
    max_asset_class_pct: float | None = None
    min_positions: int | None = None
    max_invested_pct: float | None = None
    learning_feedback_enabled: bool = False
    learning_feedback_window: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "allocated_capital": self.allocated_capital,
            "risk_profile": self.risk_profile,
            "asset_types": self.asset_types,
            "daily_rebalancing": self.daily_rebalancing,
            "benchmark": self.benchmark,
            "use_technical_indicators": self.use_technical_indicators,
            "stop_loss_enabled": self.stop_loss_enabled,
            "stop_loss_pct": self.stop_loss_pct,
            "risk_guardrails_enabled": self.risk_guardrails_enabled,
            "max_allocation_pct": self.max_allocation_pct,
            "max_asset_class_pct": self.max_asset_class_pct,
            "min_positions": self.min_positions,
            "max_invested_pct": self.max_invested_pct,
            "learning_feedback_enabled": self.learning_feedback_enabled,
            "learning_feedback_window": self.learning_feedback_window,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AIBuildParams:
        raw_pct = payload.get("stop_loss_pct")
        max_asset = payload.get("max_allocation_pct")
        max_class = payload.get("max_asset_class_pct")
        min_pos = payload.get("min_positions")
        max_inv = payload.get("max_invested_pct")
        learn_window = payload.get("learning_feedback_window")
        return cls(
            allocated_capital=float(payload.get("allocated_capital", 10000.0)),
            risk_profile=str(payload.get("risk_profile", "balanced")),
            asset_types=str(payload.get("asset_types", AssetScope.BOTH.value)),
            daily_rebalancing=bool(payload.get("daily_rebalancing", False)),
            benchmark=str(payload.get("benchmark", settings.DEFAULT_BENCHMARK)),
            use_technical_indicators=bool(
                payload.get("use_technical_indicators", False)
            ),
            stop_loss_enabled=bool(payload.get("stop_loss_enabled", False)),
            stop_loss_pct=None if raw_pct is None else float(raw_pct),
            risk_guardrails_enabled=bool(
                payload.get("risk_guardrails_enabled", False)
            ),
            max_allocation_pct=None if max_asset is None else float(max_asset),
            max_asset_class_pct=None if max_class is None else float(max_class),
            min_positions=None if min_pos is None else int(min_pos),
            max_invested_pct=None if max_inv is None else float(max_inv),
            learning_feedback_enabled=bool(
                payload.get("learning_feedback_enabled", False)
            ),
            learning_feedback_window=(
                None if learn_window is None else int(learn_window)
            ),
        )
