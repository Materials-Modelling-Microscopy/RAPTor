"""Shared normalization and deterministic identifier utilities."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path


ELEMENTS = {
    "Cr": (24, "Chromium"),
    "Hf": (72, "Hafnium"),
    "Mo": (42, "Molybdenum"),
    "Nb": (41, "Niobium"),
    "Ta": (73, "Tantalum"),
    "Ti": (22, "Titanium"),
    "V": (23, "Vanadium"),
    "W": (74, "Tungsten"),
    "Zr": (40, "Zirconium"),
}

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d+(?:\.\d+)?)?")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:16]}"


def canonical_elements(elements: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    canonical = tuple(sorted(elements))
    if len(set(canonical)) != len(canonical):
        raise ValueError(f"Duplicate elements are not allowed: {elements}")
    unknown = [element for element in canonical if element not in ELEMENTS]
    if unknown:
        raise ValueError(f"Unknown elements: {unknown}")
    return canonical


def canonical_system_name(elements: tuple[str, ...]) -> str:
    return "-".join(elements)


def system_id(elements: tuple[str, ...]) -> str:
    return "system_" + "_".join(element.lower() for element in elements)


def _format_fraction(value: float) -> str:
    text = f"{value:.12g}"
    return text.replace(".", "p")


def canonical_formula(fractions: dict[str, float]) -> str:
    return "-".join(
        f"{element}{_format_fraction(fractions[element])}"
        for element in sorted(fractions)
    )


def composition_id(fractions: dict[str, float]) -> str:
    return stable_id("composition", canonical_formula(fractions))


def equimolar_fractions(elements: tuple[str, ...]) -> dict[str, float]:
    fraction = 1.0 / len(elements)
    return {element: fraction for element in elements}


def parse_composition_formula(formula: str) -> dict[str, float]:
    """Parse formulas such as MoNbTaW or Hf28Nb28Ti28Zr16.

    Missing coefficients are interpreted as one. Coefficients are normalized
    to atomic fractions that sum to one.
    """
    compact = formula.strip()
    matches = list(_FORMULA_TOKEN.finditer(compact))
    if not matches or "".join(match.group(0) for match in matches) != compact:
        raise ValueError(f"Could not parse composition formula: {formula!r}")

    amounts: dict[str, float] = {}
    for match in matches:
        element = match.group(1)
        if element not in ELEMENTS:
            raise ValueError(f"Unknown element {element!r} in {formula!r}")
        if element in amounts:
            raise ValueError(f"Duplicate element {element!r} in {formula!r}")
        amount = float(match.group(2)) if match.group(2) else 1.0
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError(f"Invalid amount for {element} in {formula!r}")
        amounts[element] = amount

    total = sum(amounts.values())
    return {
        element: amount / total
        for element, amount in sorted(amounts.items())
    }


def is_equimolar(fractions: dict[str, float], tolerance: float = 1e-10) -> bool:
    target = 1.0 / len(fractions)
    return all(
        math.isclose(value, target, rel_tol=0, abs_tol=tolerance)
        for value in fractions.values()
    )

