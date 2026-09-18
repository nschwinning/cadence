"""Unit tests for the Docker-style portfolio name generator."""

from __future__ import annotations

import random

from cadence.utils.name_generator import (
    ADJECTIVES,
    FAMOUS_NAMES,
    generate_unique_name,
)


def test_name_without_risk_profile_is_two_titlecase_words() -> None:
    random.seed(1)
    name = generate_unique_name()
    parts = name.split(" ")
    assert len(parts) == 2
    assert parts[0].lower() in ADJECTIVES
    assert parts[1].lower() in FAMOUS_NAMES
    assert name == name.title()


def test_name_with_risk_profile_prefixes_the_profile() -> None:
    random.seed(1)
    name = generate_unique_name(risk_profile="aggressive")
    parts = name.split(" ")
    assert len(parts) == 3
    assert parts[0] == "Aggressive"
    assert parts[1].lower() in ADJECTIVES
    assert parts[2].lower() in FAMOUS_NAMES


def test_name_is_unique_against_existing_names() -> None:
    # Force the first candidate to be taken so the generator must retry.
    random.seed(1)
    first = generate_unique_name()
    random.seed(1)
    second = generate_unique_name(existing_names={first})
    assert second != first
    assert second.lower() != first.lower()


def test_existing_names_comparison_is_case_insensitive() -> None:
    random.seed(1)
    first = generate_unique_name()
    random.seed(1)
    second = generate_unique_name(existing_names={first.upper()})
    assert second.lower() != first.lower()


def test_falls_back_to_numbered_name_when_space_exhausted() -> None:
    # Every adjective+name combination is already taken, so no unique
    # Docker-style name exists -> the generator must use the numbered fallback.
    all_combos = {
        f"{adj.title()} {name.title()}"
        for adj in ADJECTIVES
        for name in FAMOUS_NAMES
    }
    random.seed(1)
    result = generate_unique_name(existing_names=all_combos, max_attempts=50)
    assert result.startswith("Portfolio ")
    assert result.split(" ")[1].isdigit()


def test_numbered_fallback_includes_risk_profile() -> None:
    all_combos = {
        f"Aggressive {adj.title()} {name.title()}"
        for adj in ADJECTIVES
        for name in FAMOUS_NAMES
    }
    random.seed(1)
    result = generate_unique_name(
        risk_profile="aggressive", existing_names=all_combos, max_attempts=50
    )
    assert result.startswith("Aggressive Portfolio ")
