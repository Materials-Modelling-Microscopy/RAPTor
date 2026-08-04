"""Create a transparent, validated retrieval plan for a user question."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass

from .normalization import ELEMENTS, canonical_system_name, parse_composition_formula
from .tool_registry import TOOL_REGISTRY, get_tool_spec


_ELEMENT = "|".join(sorted(ELEMENTS, key=len, reverse=True))
_HYPHEN_SYSTEM = re.compile(
    rf"(?<![A-Za-z])(?:{_ELEMENT})(?:\s*-\s*(?:{_ELEMENT}))+(?![A-Za-z])"
)
_COMPACT_SYSTEM = re.compile(
    rf"(?<![A-Za-z])(?:(?:{_ELEMENT})(?:\d+(?:\.\d+)?)?){{2,}}(?![a-z])"
)
_SPACED_SYSTEM = re.compile(
    rf"(?<![A-Za-z])(?:{_ELEMENT})(?:\s+(?:{_ELEMENT})){{1,8}}(?![A-Za-z])"
)
_TEMPERATURE = re.compile(r"\b(\d+(?:\.\d+)?)\s*K\b", re.I)

_DOCUMENT_SIGNALS = {
    "according to",
    "assumption",
    "background",
    "candidate",
    "cite",
    "compositional tuning",
    "controls",
    "design rule",
    "discuss",
    "evidence",
    "explain",
    "interpret",
    "know about",
    "known about",
    "limitation",
    "literature",
    "mechanism",
    "method",
    "promising",
    "suitable",
    "tell me about",
    "what do we know",
    "why",
}
_COMPARISON_SIGNALS = {
    "compare",
    "consistent with",
    "disagree",
    "support",
    "validate",
    "versus",
    "vs",
}
_RANK_HIGH = {"highest", "largest", "maximum", "rank", "top"}
_RANK_LOW = {"lowest", "minimum", "smallest"}
_COMPONENT_COUNTS = {
    "binary": 2,
    "ternary": 3,
    "quaternary": 4,
    "quinary": 5,
    "senary": 6,
}


@dataclass(frozen=True)
class PlannedToolCall:
    """A proposed call that is checked against the reviewed registry."""

    tool_name: str
    route: str
    arguments: dict[str, object]
    missing_arguments: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class QuestionRoutePlan:
    """Auditable output of the deterministic routing layer."""

    question: str
    routes: tuple[str, ...]
    extracted_system: str | None
    extracted_temperature_K: float | None
    signals: tuple[str, ...]
    tool_calls: tuple[PlannedToolCall, ...]
    structured_coverage: str
    coverage_notes: tuple[str, ...]
    needs_clarification: bool


def _contains_any(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def extract_system(question: str) -> str | None:
    """Extract and canonicalize the first recognizable alloy composition."""
    for pattern in (_HYPHEN_SYSTEM, _COMPACT_SYSTEM, _SPACED_SYSTEM):
        match = pattern.search(question)
        if not match:
            continue
        compact = re.sub(r"[\s-]+", "", match.group(0))
        try:
            fractions = parse_composition_formula(compact)
        except ValueError:
            continue
        if len(fractions) >= 2:
            return canonical_system_name(tuple(sorted(fractions)))
    return None


def extract_temperature_K(question: str) -> float | None:
    """Extract the first explicit Kelvin temperature."""
    match = _TEMPERATURE.search(question)
    return None if match is None else float(match.group(1))


def _component_count(text: str) -> int | None:
    for label, count in _COMPONENT_COUNTS.items():
        if re.search(rf"\b{re.escape(label)}\b", text):
            return count
    return None


def _plan_call(
    tool_name: str,
    arguments: dict[str, object],
    reason: str,
) -> PlannedToolCall:
    spec = get_tool_spec(tool_name)
    missing = tuple(
        name
        for name in spec.required_parameters
        if name not in arguments or arguments[name] is None
    )
    allowed = set(spec.required_parameters) | set(spec.optional_parameters)
    unexpected = set(arguments) - allowed
    if unexpected:
        raise ValueError(
            f"Unexpected arguments for {tool_name}: {sorted(unexpected)}"
        )
    return PlannedToolCall(
        tool_name=tool_name,
        route=spec.route,
        arguments=arguments,
        missing_arguments=missing,
        reason=reason,
    )


def plan_question(question: str) -> QuestionRoutePlan:
    """Map one question to reviewed SQL and/or document tools."""
    original = question.strip()
    if not original:
        raise ValueError("question must not be empty")
    text = original.lower()
    system = extract_system(original)
    temperature = extract_temperature_K(original)
    explanatory = _contains_any(text, _DOCUMENT_SIGNALS)
    comparison = _contains_any(text, _COMPARISON_SIGNALS)
    rank_high = _contains_any(text, _RANK_HIGH)
    rank_low = _contains_any(text, _RANK_LOW)
    component_count = _component_count(text)

    calls: list[PlannedToolCall] = []
    signals: list[str] = []
    coverage_notes: list[str] = []
    structured_intent = False

    if system:
        signals.append(f"alloy_system:{system}")
    if temperature is not None:
        signals.append(f"temperature_K:{temperature:g}")
    if explanatory:
        signals.append("explanatory_language")
    if comparison:
        signals.append("comparison_language")
    if rank_high or rank_low:
        signals.append("ranking_language")

    if "database summary" in text or (
        "how many" in text
        and any(word in text for word in ("source", "document", "chunk"))
    ):
        structured_intent = True
        calls.append(
            _plan_call(
                "get_database_summary",
                {},
                "The question asks for database-level counts.",
            )
        )

    pmr_requested = (
        "pmr" in text
        or "percentage miscible region" in text
        or "compositional tuning" in text
    )
    pmr_candidate_search = (
        "mid-pmr" in text
        or "mid pmr" in text
        or "intermediate pmr" in text
        or "compositional tuning" in text
        or (
            component_count is not None
            and any(word in text for word in ("candidate", "candidates"))
        )
    )
    if pmr_candidate_search:
        signals.append("pmr_candidate_discovery")

    if pmr_requested:
        if rank_high or rank_low:
            structured_intent = True
            coverage_notes.append(
                "No reviewed tool currently ranks PMR across all systems."
            )
        elif system is not None:
            structured_intent = True
            arguments: dict[str, object] = {"system_name": system}
            if temperature is not None:
                arguments["temperature_K"] = temperature
            calls.append(
                _plan_call(
                    "get_pmr_for_system",
                    arguments,
                    "PMR is an exact system-level structured result.",
                )
            )
        elif pmr_candidate_search:
            structured_intent = True
            arguments = {
                "target_pmr_percent": 50.0,
                "tolerance_percent": 25.0,
                "limit": 10,
            }
            if component_count is not None:
                arguments["n_components"] = component_count
            if temperature is not None:
                arguments["temperature_K"] = temperature
            calls.append(
                _plan_call(
                    "find_pmr_candidates",
                    arguments,
                    (
                        "Intermediate PMR identifies systems with both "
                        "miscible and immiscible composition regions."
                    ),
                )
            )
        elif not explanatory:
            structured_intent = True
            calls.append(
                _plan_call(
                    "get_pmr_for_system",
                    {"system_name": None},
                    "A PMR lookup requires a named alloy system.",
                )
            )

    hmix_requested = (
        "hmix" in text
        or "mixing enthalpy" in text
        or "mixing enthalpies" in text
    )
    if hmix_requested and (rank_high or rank_low or system or not explanatory):
        structured_intent = True
        if rank_high or rank_low:
            calls.append(
                _plan_call(
                    "rank_binary_pairs_by_hmix",
                    {
                        "descending": not rank_low,
                    },
                    "The question asks to rank binary mixing enthalpies.",
                )
            )
        elif system and len(system.split("-")) == 2:
            calls.append(
                _plan_call(
                    "get_binary_system_summary",
                    {"system_name": system},
                    "The reviewed Hmix lookup currently covers binary systems.",
                )
            )
        else:
            coverage_notes.append(
                "Exact Hmix lookup is reviewed only for binary systems."
            )

    tmisc_requested = (
        "t_misc" in text
        or "tmisc" in text
        or "miscibility temperature" in text
        or "miscible temperature" in text
    )
    room_temperature_binary = (
        "room temperature" in text
        and "binar" in text
        and any(word in text for word in ("stable", "miscible", "stability"))
    )
    if room_temperature_binary:
        structured_intent = True
        arguments = {}
        if temperature is not None:
            arguments["room_temperature_K"] = temperature
        calls.append(
            _plan_call(
                "find_room_temperature_stable_binaries",
                arguments,
                "The question asks for binaries stable at room temperature.",
            )
        )

    threshold_binary = (
        tmisc_requested
        and "binar" in text
        and temperature is not None
        and any(phrase in text for phrase in ("above", "at least", "greater"))
    )
    if threshold_binary:
        structured_intent = True
        calls.append(
            _plan_call(
                "find_binaries_above_miscibility_temperature",
                {"minimum_temperature_K": temperature},
                "The question gives a lower T_misc threshold for binaries.",
            )
        )
    elif tmisc_requested and not room_temperature_binary:
        structured_intent = True
        if rank_high or rank_low:
            arguments = {"descending": not rank_low}
            if component_count is not None:
                arguments["n_components"] = component_count
            calls.append(
                _plan_call(
                    "rank_equimolar_miscibility_predictions",
                    arguments,
                    "The question asks to rank normalized T_misc.",
                )
            )
        else:
            calls.append(
                _plan_call(
                    "get_miscibility_predictions_for_system",
                    {"system_name": system},
                    "T_misc is stored per exact composition.",
                )
            )

    predicted_phase = (
        "predicted phase" in text
        or "phase fraction" in text
        or ("prediction" in text and "phase" in text)
    )
    experimental_phase = (
        "experimental" in text
        and any(word in text for word in ("phase", "observation", "reported"))
    )
    if predicted_phase:
        structured_intent = True
        arguments = {"system_name": system}
        if temperature is not None:
            arguments["temperature_K"] = temperature
        calls.append(
            _plan_call(
                "get_predicted_phases_for_system",
                arguments,
                "Predicted phase fractions are stored structured results.",
            )
        )
    if experimental_phase:
        structured_intent = True
        calls.append(
            _plan_call(
                "get_experimental_observations_for_system",
                {"system_name": system},
                "Experimental reports are curated sample-level records.",
            )
        )

    if "tdb" in text or "thermodynamic database" in text:
        structured_intent = True
        calls.append(
            _plan_call(
                "get_tdb_coverage",
                {"system_name": system},
                "TDB availability is registered by alloy system.",
            )
        )

    if (
        "system overview" in text
        or "what data" in text
        or "available evidence" in text
    ) and system:
        structured_intent = True
        calls.append(
            _plan_call(
                "get_system_overview",
                {"system_name": system},
                "The question asks what evidence exists for a system.",
            )
        )

    sql_calls = [call for call in calls if call.route == "sql"]
    if structured_intent and sql_calls and coverage_notes:
        structured_coverage = "partial"
    elif structured_intent and sql_calls:
        structured_coverage = "covered"
    elif structured_intent:
        structured_coverage = "unsupported"
    else:
        structured_coverage = "not_requested"

    if explanatory or comparison or not structured_intent:
        document_arguments: dict[str, object] = {"query": original}
        if system is not None:
            document_arguments["system_name"] = system
        calls.append(
            _plan_call(
                "hybrid_search",
                document_arguments,
                "Narrative evidence is needed for explanation or fallback.",
            )
        )

    # Validate every planned name against the registry one final time.
    for call in calls:
        if call.tool_name not in TOOL_REGISTRY:
            raise RuntimeError(f"Planner invented a tool: {call.tool_name}")

    routes = tuple(dict.fromkeys(call.route for call in calls))
    if structured_intent and "sql" not in routes:
        routes = ("sql", *routes)
    missing = any(call.missing_arguments for call in calls)
    return QuestionRoutePlan(
        question=original,
        routes=routes,
        extracted_system=system,
        extracted_temperature_K=temperature,
        signals=tuple(signals),
        tool_calls=tuple(calls),
        structured_coverage=structured_coverage,
        coverage_notes=tuple(coverage_notes),
        needs_clarification=missing or structured_coverage == "unsupported",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan safe Alloy Assistant retrieval tools for a question.",
    )
    parser.add_argument("question")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = plan_question(args.question)
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
