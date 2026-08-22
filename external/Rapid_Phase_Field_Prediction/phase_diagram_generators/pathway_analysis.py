from __future__ import annotations

from collections import Counter
from itertools import permutations
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pycalphad import Database

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.energy_above_hull import (
    calculate_energy_above_hull_state,
)


ACTIVE_PHASE_TOLERANCE = 1e-8


def _normalize_target_composition(
    target_composition: dict[str, float],
) -> dict[str, float]:
    composition = {
        str(element).upper(): float(fraction)
        for element, fraction in target_composition.items()
    }

    if len(composition) < 3:
        raise ValueError("Pathway analysis requires at least three elements.")
    if any(fraction <= 0.0 for fraction in composition.values()):
        raise ValueError("Every target-composition fraction must be positive.")

    total = sum(composition.values())
    if not np.isclose(total, 1.0, atol=1e-8):
        raise ValueError(
            f"Target composition must sum to 1. Current sum = {total:.12f}."
        )

    return {
        element: fraction / total
        for element, fraction in composition.items()
    }


def _subset_composition(
    target_composition: dict[str, float],
    subset: Iterable[str],
) -> dict[str, float]:
    subset = tuple(subset)
    subset_total = sum(target_composition[element] for element in subset)
    return {
        element: target_composition[element] / subset_total
        for element in target_composition
        if element in subset
    }


def generate_processing_paths(
    target_composition: dict[str, float],
) -> list[dict]:
    """
    Generate unique sequential-addition paths from binary to target alloy.

    Reversing the first two elements produces the same binary composition
    and therefore the same thermodynamic path. Such literal orders are
    retained as equivalent orders but evaluated only once.
    """
    target_composition = _normalize_target_composition(target_composition)
    elements = tuple(target_composition)
    unique_paths: dict[tuple[tuple[str, ...], ...], dict] = {}

    for order in permutations(elements):
        subset_sequence = tuple(
            tuple(sorted(order[:size]))
            for size in range(2, len(elements) + 1)
        )

        if subset_sequence not in unique_paths:
            nodes = [
                _subset_composition(target_composition, subset)
                for subset in subset_sequence
            ]
            unique_paths[subset_sequence] = {
                "representative_order": order,
                "equivalent_orders": [order],
                "subset_sequence": subset_sequence,
                "nodes": nodes,
            }
        else:
            unique_paths[subset_sequence]["equivalent_orders"].append(order)

    return list(unique_paths.values())


def _sample_path(
    nodes: list[dict[str, float]],
    elements: list[str],
    points_per_segment: int,
) -> list[dict]:
    if points_per_segment < 2:
        raise ValueError("points_per_segment must be at least 2.")

    segment_count = len(nodes) - 1
    sampled = []

    for segment_index in range(segment_count):
        start = np.asarray(
            [nodes[segment_index].get(element, 0.0) for element in elements],
            dtype=float,
        )
        end = np.asarray(
            [nodes[segment_index + 1].get(element, 0.0) for element in elements],
            dtype=float,
        )

        local_coordinates = np.linspace(0.0, 1.0, points_per_segment)
        if segment_index > 0:
            local_coordinates = local_coordinates[1:]

        for local_coordinate in local_coordinates:
            fractions = (
                (1.0 - local_coordinate) * start
                + local_coordinate * end
            )
            fractions = np.clip(fractions, 0.0, 1.0)
            fractions = fractions / fractions.sum()
            path_coordinate = (
                segment_index + float(local_coordinate)
            ) / segment_count

            sampled.append(
                {
                    "path_coordinate": path_coordinate,
                    "composition": fractions,
                }
            )

    return sampled


def _active_phase_fractions(equilibrium_result) -> list[dict]:
    phase_names = np.asarray(equilibrium_result.Phase.values).ravel()
    phase_fractions = np.asarray(
        equilibrium_result.NP.values,
        dtype=float,
    ).ravel()

    active = []
    for phase_name, phase_fraction in zip(phase_names, phase_fractions):
        phase_name = str(phase_name).strip()
        if (
            phase_name
            and phase_name not in {"nan", "_FAKE_"}
            and np.isfinite(phase_fraction)
            and phase_fraction > ACTIVE_PHASE_TOLERANCE
        ):
            active.append((phase_name, float(phase_fraction)))

    if not active:
        raise ValueError("No active equilibrium phases were found.")

    fraction_sum = sum(fraction for _, fraction in active)
    active = [
        (phase_name, fraction / fraction_sum)
        for phase_name, fraction in active
    ]

    total_counts = Counter(phase_name for phase_name, _ in active)
    current_counts: Counter[str] = Counter()
    rows = []

    for phase_name, phase_fraction in active:
        current_counts[phase_name] += 1
        phase_label = phase_name
        if total_counts[phase_name] > 1:
            phase_label = f"{phase_name}#{current_counts[phase_name]}"

        rows.append(
            {
                "phase_label": phase_label,
                "phase_model": phase_name,
                "phase_fraction": phase_fraction,
            }
        )

    return rows


def _composition_key(composition: np.ndarray) -> tuple[float, ...]:
    return tuple(np.round(np.asarray(composition, dtype=float), 12))


def _integrated_burden(
    path_coordinates: np.ndarray,
    energy_above_hull: np.ndarray,
) -> float:
    coordinates = np.asarray(path_coordinates, dtype=float)
    energies = np.asarray(energy_above_hull, dtype=float)
    if coordinates.ndim != 1 or energies.ndim != 1:
        raise ValueError("Path coordinates and energies must be one-dimensional.")
    if len(coordinates) != len(energies) or len(coordinates) < 2:
        raise ValueError("A path requires at least two paired coordinate values.")
    if np.any(np.diff(coordinates) <= 0.0):
        raise ValueError("Path coordinates must be strictly increasing.")
    return float(np.trapezoid(energies, coordinates))


def analyze_processing_paths(
    tdb_path: str | Path,
    target_composition: dict[str, float],
    temperature: float,
    *,
    points_per_segment: int = 9,
    pressure: float = 101325.0,
) -> dict:
    """
    Calculate thermodynamic burden and phase fractions for every path.

    Every stage occupies an equal interval of a normalized path coordinate
    from zero to one. The path-integrated burden is therefore directly
    comparable between elemental-addition sequences for the same target
    system.

    Returns
    -------
    dict
        ``paths`` contains one integrated burden per unique path.
        ``path_points`` contains composition and energy along each path.
        ``phase_fractions`` contains the equilibrium phase breakdown.
        ``system_metrics`` contains the mean path burden and variance across
        path burdens, the two quantities used for inter-system comparison.
    """
    target_composition = _normalize_target_composition(target_composition)
    if temperature <= 0.0:
        raise ValueError("temperature must be positive.")

    tdb_path = Path(tdb_path)
    if not tdb_path.is_file():
        raise FileNotFoundError(f"TDB file not found: {tdb_path}")

    elements = list(target_composition)
    paths = generate_processing_paths(target_composition)

    sampled_paths = []
    unique_compositions: dict[tuple[float, ...], np.ndarray] = {}
    for path_id, path in enumerate(paths):
        samples = _sample_path(path["nodes"], elements, points_per_segment)
        sampled_paths.append(samples)
        for sample in samples:
            key = _composition_key(sample["composition"])
            unique_compositions.setdefault(key, sample["composition"])

    database = Database(str(tdb_path))
    energy_cache: dict[tuple[float, ...], float] = {}
    phase_cache: dict[tuple[float, ...], list[dict]] = {}
    for key, composition in unique_compositions.items():
        state = calculate_energy_above_hull_state(
            database=database,
            composition={
                element: float(composition[index])
                for index, element in enumerate(elements)
            },
            temperature=temperature,
            parent_phase="BCC_A2",
            pressure=pressure,
        )
        energy_cache[key] = state["energy_above_hull_meV_per_atom"]
        phase_cache[key] = _active_phase_fractions(
            state["equilibrium_result"]
        )

    path_rows = []
    point_rows = []
    phase_rows = []

    for path_id, (path, samples) in enumerate(zip(paths, sampled_paths)):
        coordinates = np.asarray(
            [sample["path_coordinate"] for sample in samples],
            dtype=float,
        )
        burdens = np.asarray(
            [
                energy_cache[_composition_key(sample["composition"])]
                for sample in samples
            ],
            dtype=float,
        )
        integrated_burden = _integrated_burden(coordinates, burdens)
        path_label = " → ".join(
            "-".join(subset)
            for subset in path["subset_sequence"]
        )

        path_rows.append(
            {
                "path_id": path_id,
                "path": path_label,
                "starting_binary": "-".join(path["subset_sequence"][0]),
                "representative_order": path["representative_order"],
                "equivalent_orders": tuple(path["equivalent_orders"]),
                "integrated_burden_meV_per_atom": integrated_burden,
            }
        )

        for sample in samples:
            composition = sample["composition"]
            key = _composition_key(composition)
            common = {
                "path_id": path_id,
                "path": path_label,
                "path_coordinate": float(sample["path_coordinate"]),
            }
            composition_values = {
                f"X_{element}": float(composition[index])
                for index, element in enumerate(elements)
            }
            point_rows.append(
                {
                    **common,
                    **composition_values,
                    "energy_above_hull_meV_per_atom": energy_cache[key],
                }
            )

            for phase in phase_cache[key]:
                phase_rows.append(
                    {
                        **common,
                        **composition_values,
                        **phase,
                    }
                )

    path_table = pd.DataFrame(path_rows).sort_values(
        "integrated_burden_meV_per_atom",
        ignore_index=True,
    )
    path_burdens = path_table[
        "integrated_burden_meV_per_atom"
    ].to_numpy(dtype=float)

    return {
        "target_composition": target_composition,
        "temperature_K": float(temperature),
        "paths": path_table,
        "path_points": pd.DataFrame(point_rows),
        "phase_fractions": pd.DataFrame(phase_rows),
        "system_metrics": {
            "mean_integrated_burden_meV_per_atom": float(
                np.mean(path_burdens)
            ),
            "path_dependence_variance_meV2_per_atom2": float(
                np.var(path_burdens)
            ),
        },
    }


def plot_path_energy_profiles(
    path_points: pd.DataFrame,
    path_ids: Iterable[int] | None = None,
):
    """Plot solid-solution energy above hull for selected paths."""
    plot_data = path_points.copy()
    if path_ids is not None:
        selected = set(int(path_id) for path_id in path_ids)
        plot_data = plot_data[plot_data["path_id"].isin(selected)]
    if plot_data.empty:
        raise ValueError("No pathway energy data are available to plot.")

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    groups = list(plot_data.groupby(["path_id", "path"], sort=False))
    colors = plt.get_cmap("tab10", max(1, len(groups)))

    for color_index, ((_, path_label), group) in enumerate(groups):
        group = group.sort_values("path_coordinate")
        ax.plot(
            group["path_coordinate"],
            group["energy_above_hull_meV_per_atom"],
            marker="o",
            markersize=4.5,
            linewidth=1.8,
            color=colors(color_index),
            label=path_label,
        )

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(bottom=0.0)
    ax.set_xlabel("Normalized processing path")
    ax.set_ylabel("BCC_A2 energy above hull (meV/atom)")
    ax.set_title("Solid-solution burden along each path", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout()
    return fig


def plot_path_phase_fractions(
    phase_fractions: pd.DataFrame,
    path_id: int,
):
    """Plot active equilibrium phase fractions along one processing path."""
    plot_data = phase_fractions[
        phase_fractions["path_id"] == int(path_id)
    ].copy()
    if plot_data.empty:
        raise ValueError(f"No phase-fraction data are available for path {path_id}.")

    path_label = str(plot_data["path"].iloc[0])
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    groups = list(plot_data.groupby("phase_label", sort=True))
    colors = plt.get_cmap("tab10", max(1, len(groups)))
    for color_index, (phase_label, group) in enumerate(groups):
        grouped = group.groupby("path_coordinate", as_index=False)[
            "phase_fraction"
        ].sum()
        ax.scatter(
            grouped["path_coordinate"],
            grouped["phase_fraction"],
            label=phase_label,
            color=colors(color_index),
            s=42,
            alpha=0.88,
            edgecolors="white",
            linewidths=0.55,
        )
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Normalized processing path")
    ax.set_ylabel("Equilibrium phase fraction")
    ax.set_title(path_label, loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout()
    return fig


def plot_system_path_burden_landscape(
    system_metrics: pd.DataFrame,
    *,
    system_column: str = "System",
    mean_column: str = "mean_integrated_burden_meV_per_atom",
    variance_column: str = "path_dependence_variance_meV2_per_atom2",
    label_limit: int = 40,
):
    """Scatter systems by mean path burden and between-path variance.

    The figure intentionally assigns no desirability direction to either axis.
    It is a population-context view rather than a ranking or Pareto plot.
    """
    required = {system_column, mean_column, variance_column}
    missing = required.difference(system_metrics.columns)
    if missing:
        raise ValueError(
            "Path-burden landscape is missing columns: "
            + ", ".join(sorted(missing))
        )
    plot_data = system_metrics.dropna(
        subset=[mean_column, variance_column]
    ).copy()
    if plot_data.empty:
        raise ValueError("No complete system pathway metrics are available to plot.")

    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    ax.scatter(
        plot_data[mean_column],
        plot_data[variance_column],
        s=62,
        color="#5969c7",
        alpha=0.82,
        edgecolors="white",
        linewidths=0.7,
    )
    if len(plot_data) <= label_limit:
        for _, row in plot_data.iterrows():
            ax.annotate(
                str(row[system_column]),
                (row[mean_column], row[variance_column]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7.5,
                alpha=0.82,
            )
    ax.set_xlabel("Mean integrated path burden (meV/atom)")
    ax.set_ylabel("Variance in path burden ((meV/atom)²)")
    ax.set_title("Path-burden landscape", loc="left", fontweight="bold")
    ax.grid(alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig
