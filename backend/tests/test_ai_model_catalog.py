"""Tests for the per-session AI model catalog."""

from __future__ import annotations

from cadence.config import settings
from cadence.paper_trading.constants import (
    AI_MODEL_DISPLAY_NAMES,
    AIModel,
    ai_model_display_name,
)

# --------------------------------------------------------------------------- #
# 1.1 Catalog
# --------------------------------------------------------------------------- #


def test_every_model_has_a_non_empty_display_name() -> None:
    for member in AIModel:
        assert ai_model_display_name(member)
    # The display-name map covers exactly the enum members, nothing extra/missing.
    assert set(AI_MODEL_DISPLAY_NAMES) == set(AIModel)


def test_catalog_offers_both_providers() -> None:
    # OpenAI (gpt-*) and Anthropic (claude-*) models are both selectable entries,
    # each with a stable identifier and display name.
    ids = {m.value for m in AIModel}
    assert any(i.startswith("gpt-") for i in ids)
    anthropic_ids = {
        AIModel.CLAUDE_SONNET_5_5.value,
        AIModel.CLAUDE_OPUS_5_5.value,
        AIModel.CLAUDE_HAIKU_4_5.value,
    }
    assert anthropic_ids <= ids
    for member in (
        AIModel.CLAUDE_SONNET_5_5,
        AIModel.CLAUDE_OPUS_5_5,
        AIModel.CLAUDE_HAIKU_4_5,
    ):
        assert member.value.startswith("claude-")
        assert ai_model_display_name(member)


# --------------------------------------------------------------------------- #
# 1.4 Default + backfill ids are catalog members
# --------------------------------------------------------------------------- #


def test_configured_default_is_a_catalog_member() -> None:
    # The default new builds freeze (gpt-6-luna) must be selectable.
    assert settings.AI_PORTFOLIO_MODEL == AIModel.GPT_6_LUNA.value
    assert settings.AI_PORTFOLIO_MODEL in {m.value for m in AIModel}


def test_session_backfill_id_is_a_catalog_member() -> None:
    # The migration backfills pre-existing sessions to gpt-5-mini; it must remain a
    # catalog member so no backfilled session holds an unselectable id.
    assert AIModel.GPT_5_MINI.value == "gpt-5-mini"
    assert AIModel.GPT_5_MINI in set(AIModel)
