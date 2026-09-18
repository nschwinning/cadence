"""Docker-style name generator for portfolios.

Ported from the sibling trading-bot app so AI-built portfolios get distinct,
human-friendly names (e.g. "Aggressive Jolly Wozniak") instead of the generic,
colliding names the AI produces. Pure functions: given the same RNG seed and
inputs they are deterministic and unit-testable.
"""

from __future__ import annotations

import random

ADJECTIVES = [
    "admiring", "agile", "amazing", "bold", "brave", "bright", "calm", "charming",
    "clever", "confident", "cool", "daring", "dazzling", "determined", "eager",
    "elegant", "epic", "faithful", "fearless", "focused", "friendly", "gallant",
    "gifted", "golden", "graceful", "happy", "hopeful", "inspiring", "jolly",
    "keen", "kind", "laughing", "lively", "loving", "lucid", "lucky", "magical",
    "merry", "mighty", "modest", "noble", "optimistic", "peaceful", "pensive",
    "polished", "practical", "proud", "quirky", "radiant", "relaxed", "reverent",
    "romantic", "serene", "sharp", "shining", "silly", "sleek", "smooth", "sparkling",
    "spirited", "stoic", "stunning", "sunny", "swift", "tender", "thirsty", "trusting",
    "upbeat", "vibrant", "vigilant", "vivid", "warm", "wise", "witty", "wonderful",
    "zealous", "zen",
]

SCIENTISTS_AND_INVENTORS = [
    "archimedes", "aristotle", "babbage", "bell", "bohr", "brahe", "curie",
    "darwin", "davinci", "edison", "einstein", "euler", "faraday", "fermi",
    "feynman", "fibonacci", "franklin", "galileo", "gauss", "hawking", "heisenberg",
    "hopper", "hypatia", "kepler", "leibniz", "lovelace", "maxwell", "mendel",
    "mendeleev", "morse", "newton", "noether", "ohm", "pascal", "pasteur",
    "pauli", "planck", "ptolemy", "pythagoras", "ramanujan", "rutherford",
    "schrodinger", "tesla", "turing", "watt", "wozniak",
]

INVESTORS_AND_ECONOMISTS = [
    "ackman", "bogle", "buffett", "dalio", "druckenmiller", "fisher", "friedman",
    "graham", "greenblatt", "icahn", "keynes", "klarman", "lynch", "marks",
    "munger", "pabrai", "rogers", "rothschild", "schwab", "simons", "smith",
    "soros", "templeton", "tudor", "vanguard",
]

FAMOUS_NAMES = SCIENTISTS_AND_INVENTORS + INVESTORS_AND_ECONOMISTS


def generate_unique_name(
    risk_profile: str | None = None,
    existing_names: set[str] | None = None,
    max_attempts: int = 100,
) -> str:
    """Generate a unique Docker-style portfolio name.

    Args:
        risk_profile: Optional risk profile to prefix (e.g. "aggressive").
        existing_names: Names to avoid; comparison is case-insensitive.
        max_attempts: Tries before falling back to a numbered name.

    Returns:
        A unique name like "Aggressive Jolly Wozniak" (with a risk profile) or
        "Jolly Wozniak" (without). Falls back to "<Profile> Portfolio <NNNN>"
        when the adjective/name space cannot yield an unused combination.
    """
    existing = existing_names or set()
    taken = {n.lower() for n in existing}

    for _ in range(max_attempts):
        adjective = random.choice(ADJECTIVES)
        name = random.choice(FAMOUS_NAMES)

        if risk_profile:
            full_name = f"{risk_profile.title()} {adjective.title()} {name.title()}"
        else:
            full_name = f"{adjective.title()} {name.title()}"

        if full_name.lower() not in taken:
            return full_name

    suffix = random.randint(1000, 9999)
    if risk_profile:
        return f"{risk_profile.title()} Portfolio {suffix}"
    return f"Portfolio {suffix}"
