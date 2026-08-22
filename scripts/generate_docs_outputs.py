"""Generate the representative calculation outputs embedded in the API docs.

The settings are intentionally coarse enough for documentation builds while
remaining scientifically recognizable. Run this script from the repository
root after calculation behavior or plotting changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import raptor_alloys as rap


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "assets" / "outputs"
INTERACTIONS = rap.TDB_DIR.parent / "spinodal" / "binary_interactions.json"


def save_figure(figure, name: str) -> None:
    figure.savefig(OUTPUT_DIR / name, dpi=170, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {}

    phase = rap.run_phase_fraction_temperature_prediction(
        alloy_system=["Cr", "W"],
        mol_ratio=[0.5, 0.5],
        temperature_min=300,
        temperature_max=2500,
        temperature_step=200,
        tdb_dir=rap.TDB_DIR,
    )
    phase.data.to_csv(OUTPUT_DIR / "phase-stability.csv", index=False)
    phase.energy_above_hull_data.to_csv(
        OUTPUT_DIR / "phase-stability-energy.csv", index=False
    )
    save_figure(phase.figure, "phase-stability.png")
    save_figure(phase.energy_above_hull_figure, "phase-stability-energy.png")
    summary["phase_stability"] = {
        "composition": phase.composition,
        "metastable_temperature_K": phase.metastable_temperature,
        "stable_temperature_K": phase.stable_temperature,
        "columns": phase.data.columns.tolist(),
    }

    diagram = rap.run_phase_diagram_prediction(
        alloy_system=["Cr", "W"],
        tdb_dir=rap.TDB_DIR,
        temperature_min=300,
        temperature_max=2500,
        temperature_step=100,
        composition_step=0.05,
    )
    save_figure(diagram.figure, "phase-diagram.png")
    summary["phase_diagram"] = {
        "composition": diagram.composition,
        "diagram_type": diagram.diagram_type,
    }

    splitting = rap.run_composition_splitting_prediction(
        alloy_system=["Cr", "W"],
        mols=[[0.5, 0.5]],
        temperatures=[1000, 1800],
        tdb_dir=rap.TDB_DIR,
    )
    splitting_tables = []
    for result in splitting.results:
        name = f"composition-splitting-{result.temperature:.0f}K"
        result.data.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
        save_figure(result.figure, f"{name}.png")
        table = result.data.copy()
        table.insert(0, "temperature_K", result.temperature)
        splitting_tables.append(table)
    pd.concat(splitting_tables, ignore_index=True).to_csv(
        OUTPUT_DIR / "composition-splitting.csv", index=False
    )
    summary["composition_splitting"] = {
        "alloy_system": splitting.alloy_system,
        "temperatures_K": [result.temperature for result in splitting.results],
    }

    spinodal = rap.run_spinodal_analysis(
        alloy_system=["Cr", "Ta", "Ti", "W"],
        mol_ratio=[0.25, 0.25, 0.25, 0.25],
        lattice="BCC",
        temperature_min=300,
        temperature_max=3000,
        temperature_step=100,
        mode_temperature=1500,
        interaction_data_path=INTERACTIONS,
    )
    spinodal.spectrum_data.to_csv(OUTPUT_DIR / "spinodal-spectrum.csv", index=False)
    save_figure(spinodal.eigenvalue_figure, "spinodal-spectrum.png")
    save_figure(spinodal.mode_figure, "spinodal-mode.png")
    summary["spinodal"] = {
        "spinodal_temperature_K": spinodal.spinodal_temperature,
        "mode_temperature_K": spinodal.mode_temperature,
        "interpretation": spinodal.interpretation,
    }

    symplex = rap.run_symplex_prediction(
        alloy_system=["Cr", "Mo", "Nb", "Ta"],
        temperature=1500,
        constraint_element="Cr",
        property_name="Minimum Spinodal Eigenvalue",
    )
    save_figure(symplex.figure, "symplex.png")
    summary["symplex"] = {
        "alloy_system": symplex.alloy_system,
        "temperature_K": symplex.temperature,
        "property_name": symplex.property_name,
    }

    pathways = rap.run_pathway_analysis(
        alloy_system=["Cr", "Mo", "Nb"],
        mol_ratio=[1 / 3, 1 / 3, 1 / 3],
        temperature=1500,
        tdb_dir=rap.TDB_DIR,
        points_per_segment=3,
    )
    pathways.paths.to_csv(OUTPUT_DIR / "pathways.csv", index=False)
    pathways.path_points.to_csv(OUTPUT_DIR / "pathway-points.csv", index=False)
    summary["pathways"] = {
        "starting_binaries": pathways.starting_binaries,
        "mean_integrated_burden_meV_atom": pathways.mean_integrated_burden,
        "path_dependence_variance_meV2_atom2": pathways.path_dependence_variance,
    }

    system = rap.run_alloy_system_summary(
        alloy_system=["Cr", "W"],
        reference_temperature=1500,
        temperature_min=300,
        temperature_max=2400,
        temperature_step=300,
        tdb_dir=rap.TDB_DIR,
        interaction_data_path=INTERACTIONS,
        max_sample_points=30,
    )
    system.subsystems.to_csv(OUTPUT_DIR / "system-summary.csv", index=False)
    system.sample_phase_breakdown.to_csv(
        OUTPUT_DIR / "system-phase-breakdown.csv", index=False
    )
    summary["system_summary"] = {
        "alloy_system": system.alloy_system,
        "reference_temperature_K": system.reference_temperature,
        "miscible_percentage": system.miscible_percentage,
        "sample_points": system.sample_points,
        "evaluated_sample_points": system.evaluated_sample_points,
    }

    with TemporaryDirectory(prefix="raptor-docs-") as temporary_dir:
        comparison = rap.run_inter_system_comparison(
            element_pool=["Cr", "Mo", "W"],
            order=2,
            selected_metrics=["active_phase_count"],
            primary_metric="active_phase_count",
            reference_temperature=1500,
            temperature_min=300,
            temperature_max=2400,
            temperature_step=300,
            lattice="BCC",
            tdb_dir=rap.TDB_DIR,
            interaction_data_path=INTERACTIONS,
            cache_path=Path(temporary_dir) / "comparison-cache.sqlite",
            max_sample_points=20,
        )
    comparison.data.to_csv(OUTPUT_DIR / "system-comparison.csv", index=False)
    summary["system_comparison"] = {
        "candidate_count": comparison.candidate_count,
        "complete_count": comparison.complete_count,
        "pareto_count": comparison.pareto_count,
        "cache_hits": comparison.cache_hits,
        "cache_misses": comparison.cache_misses,
    }

    (OUTPUT_DIR / "representative-output-summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
