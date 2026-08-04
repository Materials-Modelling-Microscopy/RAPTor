"""Reviewed capabilities that an Alloy Assistant planner may invoke."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Stable public contract for one safe assistant capability."""

    name: str
    route: str
    description: str
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...] = ()


TOOL_SPECS = (
    ToolSpec(
        "get_database_summary",
        "sql",
        "Count the main curated structured and document entities.",
        (),
    ),
    ToolSpec(
        "get_system_overview",
        "sql",
        "Summarize available structured evidence for one alloy system.",
        ("system_name",),
    ),
    ToolSpec(
        "get_binary_system_summary",
        "sql",
        "Return Hmix and equimolar miscibility data for one binary system.",
        ("system_name",),
    ),
    ToolSpec(
        "get_pairwise_interactions_for_system",
        "sql",
        (
            "Return all stored binary 0 K mixing enthalpies among the "
            "elements in a named multicomponent alloy system."
        ),
        ("system_name",),
    ),
    ToolSpec(
        "rank_binary_pairs_by_hmix",
        "sql",
        "Rank binary systems by DFT mixing enthalpy in eV/atom.",
        (),
        ("limit", "descending"),
    ),
    ToolSpec(
        "find_room_temperature_stable_binaries",
        "sql",
        "Find binaries with predicted T_misc at or below a temperature.",
        (),
        ("room_temperature_K",),
    ),
    ToolSpec(
        "find_binaries_above_miscibility_temperature",
        "sql",
        "Find binaries at or above a minimum normalized T_misc.",
        ("minimum_temperature_K",),
    ),
    ToolSpec(
        "get_miscibility_predictions_for_system",
        "sql",
        "Return composition-level T_misc predictions for one system.",
        ("system_name",),
        ("equimolar_only",),
    ),
    ToolSpec(
        "rank_equimolar_miscibility_predictions",
        "sql",
        "Rank validated equimolar compositions by normalized T_misc.",
        (),
        ("limit", "descending", "n_components"),
    ),
    ToolSpec(
        "get_pmr_for_system",
        "sql",
        "Return PMR percentages for one system and optional exact temperature.",
        ("system_name",),
        ("temperature_K",),
    ),
    ToolSpec(
        "find_pmr_candidates",
        "sql",
        (
            "Find distinct alloy systems with PMR near a target percentage; "
            "optionally filter component count and temperature."
        ),
        (),
        (
            "n_components",
            "target_pmr_percent",
            "tolerance_percent",
            "temperature_K",
            "limit",
        ),
    ),
    ToolSpec(
        "get_predicted_phases_for_system",
        "sql",
        "Return predicted phase fractions for one system.",
        ("system_name",),
        ("temperature_K",),
    ),
    ToolSpec(
        "get_experimental_observations_for_system",
        "sql",
        "Return source-preserving experimental phase reports for one system.",
        ("system_name",),
    ),
    ToolSpec(
        "get_tdb_coverage",
        "sql",
        "Return TDB availability and metadata for one alloy system.",
        ("system_name",),
    ),
    ToolSpec(
        "hybrid_search",
        "documents",
        "Retrieve a fused lexical and semantic evidence packet with citations.",
        ("query",),
        (
            "limit",
            "source_class",
            "system_name",
            "max_per_document",
            "max_total_words",
        ),
    ),
)

TOOL_REGISTRY = {spec.name: spec for spec in TOOL_SPECS}


def get_tool_spec(name: str) -> ToolSpec:
    """Return a reviewed tool contract; reject invented tool names."""
    try:
        return TOOL_REGISTRY[name]
    except KeyError as error:
        raise ValueError(f"Unknown reviewed tool: {name}") from error
