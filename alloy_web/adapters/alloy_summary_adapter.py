from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import comb, gcd
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable
import json

import numpy as np
import pandas as pd
from pycalphad import Database, Workspace
from pycalphad import variables as v


SOLID_SOLUTION_PHASES = ("BCC_A2", "FCC_A1", "HCP_A3")
EV_PER_ATOM_TO_J_PER_MOL = 96485.0
ACTIVE_PHASE_TOLERANCE = 1e-8


@dataclass
class AlloySystemSummaryResult:
    alloy_system: list[str]
    reference_temperature: float
    miscibility_threshold: float
    sample_points: int
    evaluated_sample_points: int
    miscible_sample_points: int
    miscible_percentage: float
    sample_phase_breakdown: pd.DataFrame
    subsystems: pd.DataFrame
    intermetallics: pd.DataFrame
    binary_interactions: pd.DataFrame
    tdb_interactions: pd.DataFrame
    elapsed_seconds: float
    equilibrium_calculations: int


def _subsystems(elements: list[str]) -> Iterable[tuple[str, ...]]:
    for order in range(2, len(elements) + 1):
        yield from combinations(elements, order)


def _tdb_index(tdb_dir: Path) -> dict[frozenset[str], list[Path]]:
    index: dict[frozenset[str], list[Path]] = {}
    for path in tdb_dir.glob("*.tdb"):
        key = frozenset(part.upper() for part in path.stem.split("-") if part)
        index.setdefault(key, []).append(path)
    return index


def _resolve_tdb_path(
    elements: tuple[str, ...] | list[str],
    tdb_dir: Path,
    index: dict[frozenset[str], list[Path]],
) -> Path | None:
    exact = tdb_dir / f"{'-'.join(elements)}.tdb"
    if exact.exists():
        return exact

    candidates = index.get(frozenset(element.upper() for element in elements), [])
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.name)[0]


def resolve_tdb_for_system(
    elements: Iterable[str],
    tdb_dir: str | Path,
    index: dict[frozenset[str], list[Path]] | None = None,
) -> tuple[Path, list[str]]:
    """
    Resolve the TDB file for a set of elements whatever order they arrive in,
    and report the element order that file's name uses.

    Callers routinely hand the joined element string to pycalphad helpers that
    positionally pair mole fractions with ``name.split("-")``. Any per-element
    data must therefore be reordered onto the returned order, otherwise the
    fractions are silently assigned to the wrong elements.

    Raises FileNotFoundError when no database covers the element set.
    """
    elements = list(elements)
    tdb_dir = Path(tdb_dir)

    if index is None:
        index = _tdb_index(tdb_dir)

    tdb_path = _resolve_tdb_path(elements, tdb_dir, index)
    if tdb_path is None:
        raise FileNotFoundError(
            f"No TDB file was found for {'-'.join(elements)}."
        )

    by_upper = {element.upper(): element for element in elements}
    ordered = [
        by_upper[part.upper()]
        for part in tdb_path.stem.split("-")
        if part and part.upper() in by_upper
    ]

    if len(ordered) != len(elements):
        raise FileNotFoundError(
            f"TDB file {tdb_path.name} does not match the requested elements "
            f"{'-'.join(elements)}."
        )

    return tdb_path, ordered


def _conditions(
    components: list[str],
    mol: Iterable[float],
    temperature: float,
) -> dict:
    mol = list(mol)
    conditions = {
        v.X(component): float(mol[i])
        for i, component in enumerate(components[:-1])
    }
    conditions[v.T] = float(temperature)
    conditions[v.P] = 101325.0
    return conditions


def _classify_equilibrium(
    equilibrium_result,
    threshold: float,
) -> tuple[bool, str | None, float | None, list[str]]:
    active = _active_composition_sets(equilibrium_result)

    active_labels = [phase for phase, _ in active]
    if len(active) != 1:
        return False, None, None, active_labels

    phase, fraction = active[0]
    is_miscible = phase in SOLID_SOLUTION_PHASES and fraction >= threshold
    return is_miscible, phase if is_miscible else None, fraction, active_labels


def _active_composition_sets(equilibrium_result) -> list[tuple[str, float]]:
    phase_values = np.asarray(equilibrium_result.Phase.values).ravel()
    phase_fractions = np.asarray(equilibrium_result.NP.values, dtype=float).ravel()

    active: list[tuple[str, float]] = []
    for phase, fraction in zip(phase_values, phase_fractions):
        phase = str(phase).strip()
        if (
            phase
            and phase not in {"nan", "_FAKE_"}
            and np.isfinite(fraction)
            and fraction > ACTIVE_PHASE_TOLERANCE
        ):
            active.append((phase, float(fraction)))
    return active


def _workspace_for_system(
    db: Database,
    elements: tuple[str, ...] | list[str],
    mol: Iterable[float],
    temperature: float,
) -> tuple[Workspace, list[str]]:
    components = [element.upper() for element in elements]
    workspace = Workspace(
        database=db,
        components=components + ["VA"],
        phases=list(db.phases.keys()),
        conditions=_conditions(components, mol, temperature),
    )
    return workspace, components


def _evaluate_workspace(
    workspace: Workspace,
    updates: dict,
    threshold: float,
) -> tuple[bool, str | None, float | None, list[str]]:
    workspace.conditions.update(updates)
    return _classify_equilibrium(workspace.eq.get_dataset(), threshold)


def _scan_miscibility_temperature(
    db: Database,
    elements: tuple[str, ...],
    reference_temperature: float,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    threshold: float,
) -> dict[str, Any]:
    equimolar = [1.0 / len(elements)] * len(elements)
    workspace, _ = _workspace_for_system(
        db, elements, equimolar, temperature_min
    )

    coarse_temperatures = list(
        np.arange(
            temperature_min,
            temperature_max + 0.5 * temperature_step,
            temperature_step,
            dtype=float,
        )
    )
    temperatures = sorted(set(coarse_temperatures + [float(reference_temperature)]))

    results: dict[float, tuple[bool, str | None, float | None, list[str]]] = {}
    calculation_count = 0
    for temperature in temperatures:
        try:
            results[temperature] = _evaluate_workspace(
                workspace,
                {v.T: temperature},
                threshold,
            )
        except Exception:
            results[temperature] = (False, None, None, [])
        calculation_count += 1

    transition_temperature = None
    transition_phase = None
    transition_bound = ""
    previous_temperature = None

    for temperature in temperatures:
        is_miscible, phase, _, _ = results[temperature]
        if is_miscible:
            transition_temperature = float(temperature)
            transition_phase = phase
            if temperature == temperatures[0]:
                transition_bound = "at_or_below_minimum"
            elif previous_temperature is not None:
                low = float(previous_temperature)
                high = float(temperature)
                high_phase = phase
                while high - low > 1.0:
                    midpoint = (low + high) / 2.0
                    try:
                        midpoint_result = _evaluate_workspace(
                            workspace,
                            {v.T: midpoint},
                            threshold,
                        )
                    except Exception:
                        midpoint_result = (False, None, None, [])
                    calculation_count += 1
                    if midpoint_result[0]:
                        high = midpoint
                        high_phase = midpoint_result[1]
                    else:
                        low = midpoint
                transition_temperature = high
                transition_phase = high_phase
                transition_bound = "crossing"
            break
        previous_temperature = temperature

    reference_result = results.get(float(reference_temperature))
    if reference_result is None:
        reference_result = (False, None, None, [])

    return {
        "miscibility_temperature": transition_temperature,
        "miscibility_phase": transition_phase,
        "temperature_bound": transition_bound,
        "miscible_at_reference": reference_result[0],
        "reference_phase": reference_result[1],
        "reference_active_phases": ", ".join(reference_result[3]),
        "calculation_count": calculation_count,
    }


def _weak_compositions(total: int, parts: int, prefix: tuple[int, ...] = ()):
    if parts == 1:
        yield prefix + (total,)
        return
    for value in range(total + 1):
        yield from _weak_compositions(total - value, parts - 1, prefix + (value,))


def generate_simplex_grid(n_components: int, max_points: int = 400) -> np.ndarray:
    if n_components < 2:
        raise ValueError("A simplex grid requires at least two components.")
    if max_points < n_components:
        raise ValueError("max_points is too small to represent the simplex vertices.")

    resolution = 1
    while comb(resolution + n_components, n_components - 1) <= max_points:
        resolution += 1

    points = np.asarray(
        list(_weak_compositions(resolution, n_components)),
        dtype=float,
    )
    return points / float(resolution)


def _sample_miscible_region(
    db: Database,
    elements: list[str],
    reference_temperature: float,
    threshold: float,
    max_points: int,
) -> dict[str, Any]:
    grid = generate_simplex_grid(len(elements), max_points=max_points)
    workspace, components = _workspace_for_system(
        db,
        elements,
        grid[0],
        reference_temperature,
    )

    phase_counts: Counter[str] = Counter()
    evaluated = 0
    failures = 0
    for mol in grid:
        try:
            result = _evaluate_workspace(
                workspace,
                _conditions(components, mol, reference_temperature),
                threshold,
            )
            evaluated += 1
            if result[0] and result[1] is not None:
                phase_counts[result[1]] += 1
        except Exception:
            failures += 1

    miscible = sum(phase_counts.values())
    percentage = 100.0 * miscible / evaluated if evaluated else float("nan")
    breakdown = pd.DataFrame(
        [
            {
                "Solid solution phase": phase,
                "Miscible points": count,
                "Percent of evaluated grid": 100.0 * count / evaluated,
            }
            for phase, count in sorted(phase_counts.items())
        ]
    )

    return {
        "grid_points": len(grid),
        "evaluated": evaluated,
        "failures": failures,
        "miscible": miscible,
        "percentage": percentage,
        "breakdown": breakdown,
        "calculation_count": len(grid),
    }


def scan_miscibility_temperature(
    db: Database,
    elements: tuple[str, ...],
    reference_temperature: float,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    threshold: float = 0.99,
) -> dict[str, Any]:
    """Public entry point shared by system-level comparison views."""
    return _scan_miscibility_temperature(
        db=db,
        elements=elements,
        reference_temperature=reference_temperature,
        temperature_min=temperature_min,
        temperature_max=temperature_max,
        temperature_step=temperature_step,
        threshold=threshold,
    )


def sample_miscible_region(
    db: Database,
    elements: list[str],
    reference_temperature: float,
    threshold: float = 0.99,
    max_points: int = 400,
) -> dict[str, Any]:
    """Public entry point for the existing deterministic simplex sampler."""
    return _sample_miscible_region(
        db=db,
        elements=elements,
        reference_temperature=reference_temperature,
        threshold=threshold,
        max_points=max_points,
    )


def evaluate_equimolar_state(
    db: Database,
    elements: tuple[str, ...] | list[str],
    reference_temperature: float,
) -> dict[str, Any]:
    """Evaluate phase count and the largest individual solid-solution fraction."""
    equimolar = [1.0 / len(elements)] * len(elements)
    workspace, _ = _workspace_for_system(
        db,
        elements,
        equimolar,
        reference_temperature,
    )
    active = _active_composition_sets(workspace.eq.get_dataset())
    solid_solutions = [
        (phase, fraction)
        for phase, fraction in active
        if phase in SOLID_SOLUTION_PHASES
    ]
    largest_phase, largest_fraction = (
        max(solid_solutions, key=lambda item: item[1])
        if solid_solutions
        else (None, 0.0)
    )
    return {
        "largest_solid_solution_fraction": largest_fraction,
        "largest_solid_solution_phase": largest_phase,
        "active_phase_count": len(active),
        "active_phases": [phase for phase, _ in active],
        "calculation_count": 1,
    }


def _piecewise_expression(parameter):
    if type(parameter).__name__ == "Piecewise":
        # SymEngine stores Piecewise arguments as expr, condition, expr, condition.
        return parameter.args[0]
    return parameter


def _constant_parameter_value(parameter) -> float | None:
    expression = _piecewise_expression(parameter)
    substitutions = {symbol: 0.0 for symbol in expression.free_symbols}
    try:
        return float(expression.subs(substitutions))
    except (TypeError, ValueError):
        return None


def _display_element(element: str) -> str:
    return element[:1].upper() + element[1:].lower()


def _extract_intermetallics(db: Database, element_order: list[str]) -> pd.DataFrame:
    order_lookup = {element.upper(): index for index, element in enumerate(element_order)}
    parameter_rows = {
        row["phase_name"]: row
        for row in db._parameters.all()
        if row.get("parameter_type") == "G" and str(row.get("phase_name", "")).endswith("_MP")
    }

    rows = []
    for phase_name in sorted(name for name in db.phases if name.endswith("_MP")):
        phase = db.phases[phase_name]
        stoichiometry: dict[str, float] = {}
        for constituents, ratio in zip(phase.constituents, phase.sublattices):
            if len(constituents) != 1:
                continue
            species = next(iter(constituents))
            element = str(species.name).upper()
            stoichiometry[element] = stoichiometry.get(element, 0.0) + float(ratio)

        ordered_elements = sorted(
            stoichiometry,
            key=lambda element: order_lookup.get(element, len(order_lookup)),
        )
        integer_amounts = [int(round(stoichiometry[element])) for element in ordered_elements]
        common_divisor = 0
        for amount in integer_amounts:
            common_divisor = gcd(common_divisor, amount)
        common_divisor = max(common_divisor, 1)

        formula = "".join(
            f"{_display_element(element)}{amount if amount != 1 else ''}"
            for element, amount in zip(ordered_elements, integer_amounts)
        )
        reduced_formula = "".join(
            f"{_display_element(element)}{amount // common_divisor if amount // common_divisor != 1 else ''}"
            for element, amount in zip(ordered_elements, integer_amounts)
        )

        formation_energy = None
        parameter_row = parameter_rows.get(phase_name)
        if parameter_row is not None:
            constant = _constant_parameter_value(parameter_row["parameter"])
            total_sites = sum(stoichiometry.values())
            if constant is not None and total_sites > 0:
                formation_energy = constant / total_sites / EV_PER_ATOM_TO_J_PER_MOL

        rows.append(
            {
                "Phase": phase_name,
                "Formula": formula,
                "Reduced formula": reduced_formula,
                "Subsystem": "-".join(_display_element(element) for element in ordered_elements),
                "Formation energy (eV/atom)": formation_energy,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Phase",
                "Formula",
                "Reduced formula",
                "Subsystem",
                "Formation energy (eV/atom)",
            ]
        )

    intermetallics = pd.DataFrame(rows)
    # Multiple Materials Project entries can have the same reduced composition.
    # Retain only the lowest-energy entry at each composition.
    intermetallics = intermetallics.sort_values(
        ["Reduced formula", "Formation energy (eV/atom)", "Phase"],
        na_position="last",
    ).drop_duplicates(subset=["Reduced formula"], keep="first")
    return intermetallics.sort_values(
        ["Subsystem", "Reduced formula"], ignore_index=True
    )


def _interaction_record(interaction_data: dict, a: str, b: str) -> dict | None:
    candidates = (f"{a}-{b}", f"{b}-{a}", f"{a.upper()}-{b.upper()}", f"{b.upper()}-{a.upper()}")
    for key in candidates:
        if key in interaction_data:
            return interaction_data[key]
    return None


def _extract_binary_interactions(
    elements: list[str],
    interaction_data_path: Path,
) -> pd.DataFrame:
    with interaction_data_path.open("r", encoding="utf-8") as input_file:
        interaction_data = json.load(input_file)

    rows = []
    for a, b in combinations(elements, 2):
        record = _interaction_record(interaction_data, a, b)
        rows.append(
            {
                "Pair": f"{a}-{b}",
                "BCC (eV/atom)": None if record is None else record.get("BCC"),
                "FCC (eV/atom)": None if record is None else record.get("FCC"),
                "HCP (eV/atom)": None if record is None else record.get("HCP"),
            }
        )
    interactions = pd.DataFrame(rows)
    numeric_columns = [column for column in interactions.columns if column != "Pair"]
    interactions[numeric_columns] = interactions[numeric_columns].round(3)
    return interactions


def _extract_tdb_interactions(db: Database, element_order: list[str]) -> pd.DataFrame:
    allowed_elements = {element.upper() for element in element_order}
    rows = []
    for parameter in db._parameters.all():
        if parameter.get("parameter_type") != "L":
            continue
        if parameter.get("phase_name") not in SOLID_SOLUTION_PHASES:
            continue

        species = {
            str(item.name).upper()
            for sublattice in parameter.get("constituent_array", ())
            for item in sublattice
            if str(item.name).upper() in allowed_elements
        }
        if len(species) != 2:
            continue

        ordered_species = sorted(species, key=lambda item: element_order.index(_display_element(item)))
        value_j_mol = _constant_parameter_value(parameter["parameter"])
        rows.append(
            {
                "Pair": "-".join(_display_element(item) for item in ordered_species),
                "Solid solution phase": parameter["phase_name"],
                "Order": int(parameter.get("parameter_order", 0)),
                "L (J/mol)": value_j_mol,
                "L (eV/atom)": None if value_j_mol is None else value_j_mol / EV_PER_ATOM_TO_J_PER_MOL,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["Pair", "Solid solution phase", "Order", "L (J/mol)", "L (eV/atom)"]
        )

    interactions = pd.DataFrame(rows).sort_values(
        ["Pair", "Solid solution phase", "Order"], ignore_index=True
    )
    interactions[["L (J/mol)", "L (eV/atom)"]] = interactions[
        ["L (J/mol)", "L (eV/atom)"]
    ].round(3)
    return interactions


def run_alloy_system_summary(
    alloy_system: list[str],
    reference_temperature: float,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    tdb_dir: str | Path,
    interaction_data_path: str | Path,
    miscibility_threshold: float = 0.99,
    max_sample_points: int = 400,
) -> AlloySystemSummaryResult:
    started_at = perf_counter()
    elements = list(alloy_system)
    if len(elements) < 2 or len(elements) > 5:
        raise ValueError("The alloy summary supports systems containing 2 to 5 elements.")
    if len(set(elements)) != len(elements):
        raise ValueError("Alloy-system elements must be unique.")
    if temperature_min >= temperature_max:
        raise ValueError("Minimum temperature must be below maximum temperature.")
    if temperature_step <= 0:
        raise ValueError("Temperature step must be positive.")

    tdb_dir = Path(tdb_dir)
    interaction_data_path = Path(interaction_data_path)
    index = _tdb_index(tdb_dir)
    database_cache: dict[Path, Database] = {}
    subsystem_rows = []
    total_calculations = 0

    full_tdb_path = _resolve_tdb_path(tuple(elements), tdb_dir, index)
    if full_tdb_path is None:
        raise FileNotFoundError(f"No TDB file is available for {'-'.join(elements)}.")

    for subsystem in _subsystems(elements):
        tdb_path = _resolve_tdb_path(subsystem, tdb_dir, index)
        base_row = {
            "Subsystem": "-".join(subsystem),
            "Order": len(subsystem),
        }
        if tdb_path is None:
            subsystem_rows.append(
                {
                    **base_row,
                    "Miscibility temperature": "TDB unavailable",
                    "Miscibility temperature value (K)": None,
                    "Solid solution at transition": None,
                    f"Miscible at {reference_temperature:.0f} K": None,
                    f"Active phases at {reference_temperature:.0f} K": None,
                }
            )
            continue

        try:
            db = database_cache.setdefault(tdb_path, Database(str(tdb_path)))
            scan = _scan_miscibility_temperature(
                db=db,
                elements=subsystem,
                reference_temperature=reference_temperature,
                temperature_min=temperature_min,
                temperature_max=temperature_max,
                temperature_step=temperature_step,
                threshold=miscibility_threshold,
            )
            total_calculations += scan["calculation_count"]
            temperature = scan["miscibility_temperature"]
            if temperature is None:
                temperature_result = f"Not found through {temperature_max:.0f} K"
            elif scan["temperature_bound"] == "at_or_below_minimum":
                temperature_result = f"≤ {temperature_min:.0f} K"
            else:
                temperature_result = f"{temperature:.0f} K"

            subsystem_rows.append(
                {
                    **base_row,
                    "Miscibility temperature": temperature_result,
                    "Miscibility temperature value (K)": temperature,
                    "Solid solution at transition": scan["miscibility_phase"],
                    f"Miscible at {reference_temperature:.0f} K": scan["miscible_at_reference"],
                    f"Active phases at {reference_temperature:.0f} K": scan["reference_active_phases"],
                }
            )
        except Exception as exc:
            subsystem_rows.append(
                {
                    **base_row,
                    "Miscibility temperature": f"Calculation failed: {exc}",
                    "Miscibility temperature value (K)": None,
                    "Solid solution at transition": None,
                    f"Miscible at {reference_temperature:.0f} K": None,
                    f"Active phases at {reference_temperature:.0f} K": None,
                }
            )

    full_db = database_cache.get(full_tdb_path)
    if full_db is None:
        full_db = Database(str(full_tdb_path))

    sample = _sample_miscible_region(
        db=full_db,
        elements=elements,
        reference_temperature=reference_temperature,
        threshold=miscibility_threshold,
        max_points=max_sample_points,
    )
    total_calculations += sample["calculation_count"]

    subsystems_df = pd.DataFrame(subsystem_rows)
    intermetallics_df = _extract_intermetallics(full_db, elements)
    binary_interactions_df = _extract_binary_interactions(elements, interaction_data_path)
    tdb_interactions_df = _extract_tdb_interactions(full_db, elements)

    return AlloySystemSummaryResult(
        alloy_system=elements,
        reference_temperature=float(reference_temperature),
        miscibility_threshold=float(miscibility_threshold),
        sample_points=sample["grid_points"],
        evaluated_sample_points=sample["evaluated"],
        miscible_sample_points=sample["miscible"],
        miscible_percentage=sample["percentage"],
        sample_phase_breakdown=sample["breakdown"],
        subsystems=subsystems_df,
        intermetallics=intermetallics_df,
        binary_interactions=binary_interactions_df,
        tdb_interactions=tdb_interactions_df,
        elapsed_seconds=perf_counter() - started_at,
        equilibrium_calculations=total_calculations,
    )
