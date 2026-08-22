from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alloy_web.adapters.alloy_summary_adapter import _resolve_tdb_path, _tdb_index
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.pathway_analysis import (
    analyze_processing_paths,
)


@dataclass
class PathwayAnalysisResult:
    """Thermodynamic burdens for every unique sequential alloying pathway.

    ``mean_integrated_burden`` is in meV/atom and
    ``path_dependence_variance`` is in (meV/atom) squared.

    Attributes:
        alloy_system: Evaluated elements in caller-supplied order.
        mol_ratio: Target mole fractions paired with ``alloy_system``.
        temperature: Calculation temperature in kelvin.
        points_per_segment: Composition samples per path segment.
        tdb_path: Resolved thermodynamic database file.
        paths: One aggregate row per unique pathway.
        path_points: Sampled compositions and local burden along every path.
        phase_fractions: Equilibrium phases at sampled compositions.
        mean_integrated_burden: Mean path integral in meV/atom.
        path_dependence_variance: Between-path variance in (meV/atom) squared.
    """
    alloy_system: list[str]
    mol_ratio: list[float]
    temperature: float
    points_per_segment: int
    tdb_path: Path
    paths: pd.DataFrame
    path_points: pd.DataFrame
    phase_fractions: pd.DataFrame
    mean_integrated_burden: float
    path_dependence_variance: float

    @property
    def starting_binaries(self) -> list[str]:
        return sorted(self.paths["starting_binary"].unique())

    def path_ids_for_starting_binary(self, starting_binary: str) -> list[int]:
        rows = self.paths[self.paths["starting_binary"] == starting_binary]
        return rows["path_id"].astype(int).tolist()


def run_pathway_analysis(
    alloy_system: list[str],
    mol_ratio: list[float],
    temperature: float,
    tdb_dir: str | Path,
    points_per_segment: int = 9,
) -> PathwayAnalysisResult:
    """Calculate thermodynamic burden along sequential alloying pathways.

    Args:
        alloy_system: Three to five unique element symbols.
        mol_ratio: Positive mole fractions paired with ``alloy_system`` and
            summing to one.
        temperature: Calculation temperature in kelvin.
        tdb_dir: Directory containing RAPTor ``.tdb`` databases.
        points_per_segment: Number of sampled compositions on each path segment;
            must be at least two.

    Returns:
        Per-path summaries, sampled path points, phase fractions, and aggregate
        burden metrics.

    Raises:
        ValueError: If the system, composition, temperature, or grid is invalid.
        FileNotFoundError: If no database covers the requested elements.
    """
    if not 3 <= len(alloy_system) <= 5:
        raise ValueError("Choose between three and five elements.")
    if len(set(alloy_system)) != len(alloy_system):
        raise ValueError("Alloy-system elements must be unique.")
    if len(alloy_system) != len(mol_ratio):
        raise ValueError("Number of mole fractions must match number of elements.")
    if any(fraction <= 0.0 for fraction in mol_ratio):
        raise ValueError("Every selected element must have a positive mole fraction.")
    if not abs(sum(mol_ratio) - 1.0) < 1e-6:
        raise ValueError(
            f"Mole fractions must sum to 1. Current sum = {sum(mol_ratio):.6f}."
        )
    if temperature <= 0.0:
        raise ValueError("Temperature must be positive.")
    if points_per_segment < 2:
        raise ValueError("Use at least two points per path segment.")

    tdb_dir = Path(tdb_dir)
    tdb_path = _resolve_tdb_path(
        tuple(alloy_system),
        tdb_dir,
        _tdb_index(tdb_dir),
    )
    if tdb_path is None:
        raise FileNotFoundError(
            f"No TDB file was found for {'-'.join(alloy_system)}."
        )

    calculation = analyze_processing_paths(
        tdb_path=tdb_path,
        target_composition={
            element: float(fraction)
            for element, fraction in zip(alloy_system, mol_ratio)
        },
        temperature=float(temperature),
        points_per_segment=int(points_per_segment),
    )
    metrics = calculation["system_metrics"]

    return PathwayAnalysisResult(
        alloy_system=list(alloy_system),
        mol_ratio=[float(fraction) for fraction in mol_ratio],
        temperature=float(temperature),
        points_per_segment=int(points_per_segment),
        tdb_path=tdb_path,
        paths=calculation["paths"],
        path_points=calculation["path_points"],
        phase_fractions=calculation["phase_fractions"],
        mean_integrated_burden=metrics[
            "mean_integrated_burden_meV_per_atom"
        ],
        path_dependence_variance=metrics[
            "path_dependence_variance_meV2_per_atom2"
        ],
    )
