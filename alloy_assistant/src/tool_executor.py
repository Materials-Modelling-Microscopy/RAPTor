"""Execute validated route plans through an explicit capability whitelist."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable

from duckdb import DuckDBPyConnection

from .database import DEFAULT_DATABASE_PATH, connect
from .hybrid_retrieval import hybrid_search
from .queries import (
    find_binaries_above_miscibility_temperature,
    find_room_temperature_stable_binaries,
    find_pmr_candidates,
    get_binary_system_summary,
    get_database_summary,
    get_experimental_observations_for_system,
    get_miscibility_predictions_for_system,
    get_pairwise_interactions_for_system,
    get_pmr_for_system,
    get_predicted_phases_for_system,
    get_system_overview,
    get_tdb_coverage,
    rank_binary_pairs_by_hmix,
    rank_equimolar_miscibility_predictions,
)
from .route_question import QuestionRoutePlan, plan_question
from .tool_registry import TOOL_REGISTRY


class PlanExecutionError(RuntimeError):
    """Raised when a route plan is unsafe or incomplete."""


@dataclass(frozen=True)
class ToolExecutionResult:
    """Traceable result from one reviewed tool call."""

    tool_name: str
    route: str
    arguments: dict[str, object]
    value: object


_TOOL_FUNCTIONS: dict[str, Callable[..., object]] = {
    "get_database_summary": get_database_summary,
    "get_system_overview": get_system_overview,
    "get_binary_system_summary": get_binary_system_summary,
    "get_pairwise_interactions_for_system": (
        get_pairwise_interactions_for_system
    ),
    "rank_binary_pairs_by_hmix": rank_binary_pairs_by_hmix,
    "find_room_temperature_stable_binaries": (
        find_room_temperature_stable_binaries
    ),
    "find_binaries_above_miscibility_temperature": (
        find_binaries_above_miscibility_temperature
    ),
    "get_miscibility_predictions_for_system": (
        get_miscibility_predictions_for_system
    ),
    "rank_equimolar_miscibility_predictions": (
        rank_equimolar_miscibility_predictions
    ),
    "get_pmr_for_system": get_pmr_for_system,
    "find_pmr_candidates": find_pmr_candidates,
    "get_predicted_phases_for_system": get_predicted_phases_for_system,
    "get_experimental_observations_for_system": (
        get_experimental_observations_for_system
    ),
    "get_tdb_coverage": get_tdb_coverage,
    "hybrid_search": hybrid_search,
}

if set(_TOOL_FUNCTIONS) != set(TOOL_REGISTRY):
    missing = set(TOOL_REGISTRY) - set(_TOOL_FUNCTIONS)
    extra = set(_TOOL_FUNCTIONS) - set(TOOL_REGISTRY)
    raise RuntimeError(
        f"Tool registry/executor mismatch; missing={missing}, extra={extra}"
    )


def execute_plan(
    connection: DuckDBPyConnection,
    plan: QuestionRoutePlan,
) -> list[ToolExecutionResult]:
    """Execute a complete plan without permitting invented functions or SQL."""
    if plan.structured_coverage == "unsupported":
        raise PlanExecutionError(
            "Structured request is not covered by the reviewed tool registry: "
            + "; ".join(plan.coverage_notes)
        )
    incomplete = [
        call
        for call in plan.tool_calls
        if call.missing_arguments
    ]
    if incomplete:
        details = ", ".join(
            f"{call.tool_name}: {', '.join(call.missing_arguments)}"
            for call in incomplete
        )
        raise PlanExecutionError(f"Plan is missing required arguments: {details}")

    results: list[ToolExecutionResult] = []
    for call in plan.tool_calls:
        function = _TOOL_FUNCTIONS.get(call.tool_name)
        if function is None:
            raise PlanExecutionError(
                f"Tool is not executable: {call.tool_name}"
            )
        value = function(connection, **call.arguments)
        results.append(
            ToolExecutionResult(
                tool_name=call.tool_name,
                route=call.route,
                arguments=call.arguments,
                value=value,
            )
        )
    return results


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            key: _serializable(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {
            str(key): _serializable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan and execute reviewed Alloy Assistant tools.",
    )
    parser.add_argument("question")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")
    plan = plan_question(args.question)
    with connect(database_path, read_only=True) as connection:
        results = execute_plan(connection, plan)
    print(
        json.dumps(
            {
                "plan": _serializable(plan),
                "results": _serializable(results),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
