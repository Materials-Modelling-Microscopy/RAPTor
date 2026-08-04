"""Constrained LLM evidence planning with deterministic validation and fallback."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Protocol

from .route_question import (
    PlannedToolCall,
    QuestionRoutePlan,
    plan_question,
)
from .tool_registry import TOOL_REGISTRY, ToolSpec, get_tool_spec


MAX_PLANNED_CALLS = 8
_CANDIDATE_SIGNALS = {
    "candidate",
    "interesting",
    "promising",
    "suitable",
    "worth investigating",
    "worth studying",
    "worth pursuing",
}

PLANNING_INSTRUCTIONS = """\
Role: You plan evidence retrieval for a high-entropy-alloy research assistant.

Return a small plan using only the reviewed tools supplied by the user.
Do not answer the scientific question. Do not invent SQL or tool names.

Planning rules:
- Exact values, counts, filters, and recorded predictions require SQL tools.
- Mechanisms, interpretation, design rationale, and limitations require
  document retrieval.
- Compound questions may require both routes.
- For an assessment of a named alloy, inspect the system overview, the full
  PMR temperature profile, equimolar miscibility data, every stored pairwise
  mixing enthalpy, experimental observations, and document context.
- For compositional-tuning candidates or intermediate-PMR systems, use
  find_pmr_candidates. A target near 50% with a moderate tolerance identifies
  systems containing both miscible and immiscible regions in the sampled
  composition grid.
- Treat pairwise mixing enthalpies as evidence to inspect, not as a sufficient
  verdict by themselves.
- Put tool arguments in arguments_json as one JSON object string.
- Use the canonical system and temperature extracted by deterministic code.
- Prefer reusable evidence tools over a narrow phrase-specific workflow.
- Limit the plan to the evidence materially needed for the question.
"""


class PlanningModel(Protocol):
    """Provider-independent interface for one structured planning request."""

    def plan_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_names: tuple[str, ...],
    ) -> dict[str, object]:
        """Return a structured plan containing reviewed tool calls."""


def _tool_catalog() -> list[dict[str, object]]:
    return [
        {
            "name": spec.name,
            "route": spec.route,
            "description": spec.description,
            "required_parameters": list(spec.required_parameters),
            "optional_parameters": list(spec.optional_parameters),
        }
        for spec in TOOL_REGISTRY.values()
    ]


def _is_candidate_assessment(question: str) -> bool:
    text = question.lower()
    return any(signal in text for signal in _CANDIDATE_SIGNALS)


def _should_use_llm(plan: QuestionRoutePlan) -> bool:
    simple_exact_sql = (
        plan.routes == ("sql",)
        and plan.structured_coverage == "covered"
        and not plan.needs_clarification
        and len(plan.tool_calls) == 1
    )
    if simple_exact_sql:
        return False
    if plan.extracted_system is not None:
        return True
    return (
        len(plan.routes) > 1
        or plan.structured_coverage == "unsupported"
        or "comparison_language" in plan.signals
    )


def _normalized_arguments(
    spec: ToolSpec,
    arguments: dict[str, object],
    deterministic: QuestionRoutePlan,
) -> dict[str, object]:
    allowed = set(spec.required_parameters) | set(spec.optional_parameters)
    unexpected = set(arguments) - allowed
    if unexpected:
        raise ValueError(
            f"Unexpected arguments for {spec.name}: {sorted(unexpected)}"
        )
    normalized = {
        key: value
        for key, value in arguments.items()
        if value is not None
    }
    if "system_name" in allowed and deterministic.extracted_system is not None:
        normalized["system_name"] = deterministic.extracted_system
    if "query" in allowed:
        normalized["query"] = deterministic.question
    if (
        "temperature_K" in allowed
        and deterministic.extracted_temperature_K is not None
    ):
        normalized["temperature_K"] = (
            deterministic.extracted_temperature_K
        )
    return normalized


def _validated_call(
    tool_name: object,
    arguments: object,
    reason: object,
    deterministic: QuestionRoutePlan,
) -> PlannedToolCall:
    if not isinstance(tool_name, str) or tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Planner proposed an unknown tool: {tool_name!r}")
    if not isinstance(arguments, dict):
        raise ValueError(f"Arguments for {tool_name} must be an object")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"Planner supplied no reason for {tool_name}")
    spec = get_tool_spec(tool_name)
    normalized = _normalized_arguments(spec, arguments, deterministic)
    missing = tuple(
        name
        for name in spec.required_parameters
        if name not in normalized
    )
    if missing:
        raise ValueError(
            f"Planner omitted required arguments for {tool_name}: {missing}"
        )
    return PlannedToolCall(
        tool_name=tool_name,
        route=spec.route,
        arguments=normalized,
        missing_arguments=(),
        reason=reason.strip(),
    )


def _candidate_calls(
    deterministic: QuestionRoutePlan,
) -> list[PlannedToolCall]:
    system = deterministic.extracted_system
    if system is None:
        return []
    pmr_arguments: dict[str, object] = {"system_name": system}
    if deterministic.extracted_temperature_K is not None:
        pmr_arguments["temperature_K"] = (
            deterministic.extracted_temperature_K
        )
    definitions = [
        (
            "get_system_overview",
            {"system_name": system},
            "Establish which structured evidence exists for this system.",
        ),
        (
            "get_pmr_for_system",
            pmr_arguments,
            "Assess the system's recorded PMR behavior.",
        ),
        (
            "get_miscibility_predictions_for_system",
            {"system_name": system, "equimolar_only": True},
            "Retrieve the equimolar miscibility and melting-temperature data.",
        ),
        (
            "get_pairwise_interactions_for_system",
            {"system_name": system},
            "Inspect every stored binary mixing enthalpy within the system.",
        ),
        (
            "get_experimental_observations_for_system",
            {"system_name": system},
            "Check whether system-specific experimental evidence exists.",
        ),
        (
            "hybrid_search",
            {"query": deterministic.question, "system_name": system},
            "Retrieve interpretation, mechanisms, and limitations.",
        ),
    ]
    return [
        _validated_call(name, arguments, reason, deterministic)
        for name, arguments, reason in definitions
    ]


def _deduplicate(
    calls: list[PlannedToolCall],
) -> list[PlannedToolCall]:
    unique: list[PlannedToolCall] = []
    seen: set[tuple[str, str]] = set()
    for call in calls:
        key = (
            call.tool_name,
            json.dumps(call.arguments, sort_keys=True),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(call)
    return unique


def _ensure_candidate_evidence(
    deterministic: QuestionRoutePlan,
    proposed: list[PlannedToolCall],
) -> list[PlannedToolCall]:
    if not (
        deterministic.extracted_system
        and _is_candidate_assessment(deterministic.question)
    ):
        return proposed
    core = _candidate_calls(deterministic)
    core_names = {call.tool_name for call in core}
    extras = [call for call in proposed if call.tool_name not in core_names]
    return [*core, *extras]


def _ensure_explicit_evidence(
    deterministic: QuestionRoutePlan,
    proposed: list[PlannedToolCall],
) -> list[PlannedToolCall]:
    """Preserve complete rule-based calls for explicitly requested evidence."""
    required = [
        call
        for call in deterministic.tool_calls
        if not call.missing_arguments
    ]
    required_keys = {
        (call.tool_name, json.dumps(call.arguments, sort_keys=True))
        for call in required
    }
    extras = [
        call
        for call in proposed
        if (
            call.tool_name,
            json.dumps(call.arguments, sort_keys=True),
        )
        not in required_keys
    ]
    return [*required, *extras]


def _build_plan(
    deterministic: QuestionRoutePlan,
    payload: dict[str, object],
) -> QuestionRoutePlan:
    raw_calls = payload.get("tool_calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        raise ValueError("Planner returned no tool calls")
    if len(raw_calls) > MAX_PLANNED_CALLS:
        raise ValueError("Planner exceeded the tool-call limit")

    calls: list[PlannedToolCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            raise ValueError("Planner returned an invalid tool call")
        arguments_json = raw_call.get("arguments_json")
        if not isinstance(arguments_json, str):
            raise ValueError("Planner arguments_json must be a string")
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as error:
            raise ValueError("Planner returned invalid arguments JSON") from error
        calls.append(
            _validated_call(
                raw_call.get("tool_name"),
                arguments,
                raw_call.get("reason"),
                deterministic,
            )
        )

    calls = _ensure_explicit_evidence(deterministic, calls)
    calls = _ensure_candidate_evidence(deterministic, calls)
    calls = _deduplicate(calls)[:MAX_PLANNED_CALLS]
    routes = tuple(dict.fromkeys(call.route for call in calls))
    coverage_value = payload.get("coverage_notes", [])
    if not isinstance(coverage_value, list) or not all(
        isinstance(note, str) for note in coverage_value
    ):
        raise ValueError("Planner coverage_notes must be a string array")
    coverage_notes = tuple(
        note.strip() for note in coverage_value if note.strip()
    )
    has_sql = any(call.route == "sql" for call in calls)
    structured_coverage = (
        "partial" if has_sql and coverage_notes
        else "covered" if has_sql
        else "not_requested"
    )
    return QuestionRoutePlan(
        question=deterministic.question,
        routes=routes,
        extracted_system=deterministic.extracted_system,
        extracted_temperature_K=deterministic.extracted_temperature_K,
        signals=(*deterministic.signals, "planner:llm"),
        tool_calls=tuple(calls),
        structured_coverage=structured_coverage,
        coverage_notes=coverage_notes,
        needs_clarification=False,
    )


def _fallback_plan(
    deterministic: QuestionRoutePlan,
    error: Exception,
) -> QuestionRoutePlan:
    if (
        deterministic.extracted_system
        and _is_candidate_assessment(deterministic.question)
    ):
        calls = tuple(_candidate_calls(deterministic))
        return QuestionRoutePlan(
            question=deterministic.question,
            routes=("sql", "documents"),
            extracted_system=deterministic.extracted_system,
            extracted_temperature_K=deterministic.extracted_temperature_K,
            signals=(*deterministic.signals, "planner:deterministic_fallback"),
            tool_calls=calls,
            structured_coverage="covered",
            coverage_notes=(
                "LLM planning was unavailable; the reviewed candidate "
                "evidence checklist was used.",
            ),
            needs_clarification=False,
        )
    return replace(
        deterministic,
        signals=(*deterministic.signals, "planner:deterministic_fallback"),
        coverage_notes=(
            *deterministic.coverage_notes,
            f"LLM planning was unavailable ({type(error).__name__}); "
            "the deterministic plan was used.",
        ),
    )


def plan_question_hybrid(
    question: str,
    planning_model: PlanningModel,
) -> QuestionRoutePlan:
    """Use an LLM for nontrivial evidence planning under deterministic rules."""
    deterministic = plan_question(question)
    if not _should_use_llm(deterministic):
        return replace(
            deterministic,
            signals=(*deterministic.signals, "planner:deterministic_fast_path"),
        )

    prompt = {
        "question": deterministic.question,
        "deterministic_extraction": {
            "system_name": deterministic.extracted_system,
            "temperature_K": deterministic.extracted_temperature_K,
        },
        "reviewed_tools": _tool_catalog(),
    }
    try:
        payload = planning_model.plan_tools(
            PLANNING_INSTRUCTIONS,
            json.dumps(prompt, indent=2, sort_keys=True),
            tool_names=tuple(TOOL_REGISTRY),
        )
        return _build_plan(deterministic, payload)
    except Exception as error:
        return _fallback_plan(deterministic, error)
