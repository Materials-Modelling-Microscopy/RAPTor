from __future__ import annotations

from pathlib import Path

import pytest

from eutectics.analyze_invariant_endpoint_positions import analyze
from eutectics.process_invariant_endpoints import process


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "eutectics" / "data" / "invariant_endpoints_raw.csv"


def test_endpoint_normalization_and_ordering(tmp_path: Path) -> None:
    data, summary = process(RAW, tmp_path / "processed")

    assert summary["event_count"] == 39
    assert summary["system_count"] == 26
    assert summary["complete_three_composition_count"] == 36
    assert summary["strict_reaction_ordering_valid_count"] == 35

    ag_pt = data.loc[data["event_id"].eq("Ag-Pt_P01")].iloc[0]
    assert bool(ag_pt["peritectic_ordering_valid"])
    assert (
        min(ag_pt["x_liquid_at_fraction"], ag_pt["x_reactant_solid_at_fraction"])
        < ag_pt["x_product_solid_at_fraction"]
        < max(ag_pt["x_liquid_at_fraction"], ag_pt["x_reactant_solid_at_fraction"])
    )

    ge_in = data.loc[data["event_id"].eq("Ge-In_E01")].iloc[0]
    assert ge_in["x_liquid_at_fraction"] == pytest.approx(0.999954)
    assert bool(ge_in["eutectic_ordering_valid"])

    in_mg = data.loc[data["event_id"].eq("In-Mg_P01")].iloc[0]
    assert not bool(in_mg["peritectic_ordering_valid"])


def test_solid_span_separates_matched_reaction_geometry(tmp_path: Path) -> None:
    processed_dir = tmp_path / "processed"
    _, _ = process(RAW, processed_dir)
    _, systems, summary = analyze(
        processed_dir / "invariant_endpoints_normalized.csv", tmp_path / "analysis"
    )

    comparison = summary["system_median_comparisons"]["solid_span"]
    assert comparison["eutectic_n"] == 12
    assert comparison["peritectic_n"] == 11
    assert comparison["eutectic_median"] > comparison["peritectic_median"]
    assert comparison["auc_eutectic_if_higher"] > 0.85
    assert systems["solid_span"].notna().all()
