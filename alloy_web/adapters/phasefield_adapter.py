from dataclasses import dataclass
from pathlib import Path
from typing import Any
import io

import pandas as pd
import matplotlib.figure

from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.temperature_profile_per_composition import generate_phase_fraction_temperature_profile
from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.composition_profile_per_temperature import generate_composition_splitting_profile
from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.phase_diagram_plotters import generate_binary_phase_diagram, generate_ternary_phase_diagram


@dataclass
class PhaseFractionTemperatureResult:
    composition: str
    mol_ratio: list[float]
    temp_range: tuple[float, float, float]
    data: pd.DataFrame
    figure: matplotlib.figure.Figure

    def to_csv_bytes(self) -> bytes:
        return self.data.to_csv(index=False).encode("utf-8")

    def to_png_bytes(self) -> bytes:
        buffer = io.BytesIO()
        self.figure.savefig(buffer, format="png", dpi=300, bbox_inches="tight")
        buffer.seek(0)
        return buffer.getvalue()


def run_phase_fraction_temperature_prediction(
    alloy_system: list[str],
    mol_ratio: list[float],
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    tdb_dir: str | Path,
) -> PhaseFractionTemperatureResult:
    """
    Adapter for phase fraction vs temperature calculation.
    """

    if len(alloy_system) < 2:
        raise ValueError("Choose at least two elements.")

    if len(alloy_system) != len(mol_ratio):
        raise ValueError(
            "Number of mole fractions must match number of elements."
        )

    if not abs(sum(mol_ratio) - 1.0) < 1e-6:
        raise ValueError(
            f"Mole fractions must sum to 1. Current sum = {sum(mol_ratio):.6f}"
        )

    composition = "-".join(alloy_system)
    temp_range = (
        float(temperature_min),
        float(temperature_max),
        float(temperature_step),
    )

    data, fig = generate_phase_fraction_temperature_profile(
        composition=composition,
        mol_ratio=mol_ratio,
        input_file_path=tdb_dir,
        temp_range=temp_range,
    )

    return PhaseFractionTemperatureResult(
        composition=composition,
        mol_ratio=mol_ratio,
        temp_range=temp_range,
        data=data,
        figure=fig,
    )

@dataclass
class CompositionSplittingSingleResult:
    temperature: float
    data: pd.DataFrame
    figure: matplotlib.figure.Figure

    def to_csv_bytes(self) -> bytes:
        return self.data.to_csv(index=False).encode("utf-8")

    def to_png_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        buf.seek(0)
        return buf.getvalue()


@dataclass
class CompositionSplittingResult:
    alloy_system: list[str]
    mols: list[list[float]]
    results: list[CompositionSplittingSingleResult]


def run_composition_splitting_prediction(
    alloy_system: list[str],
    mols: list[list[float]],
    temperatures: list[float],
    tdb_dir: str | Path,
) -> CompositionSplittingResult:
    composition = "-".join(alloy_system)

    if len(temperatures) == 0:
        raise ValueError("Provide at least one temperature.")

    if len(temperatures) > 3:
        raise ValueError("At most 3 temperatures are supported.")

    results = []

    for temperature in temperatures:
        df, fig = generate_composition_splitting_profile(
            composition=composition,
            mols=mols,
            temperature=float(temperature),
            tdb_dir=tdb_dir,
        )

        results.append(
            CompositionSplittingSingleResult(
                temperature=float(temperature),
                data=df,
                figure=fig,
            )
        )

    return CompositionSplittingResult(
        alloy_system=alloy_system,
        mols=mols,
        results=results,
    )



@dataclass
class PhaseDiagramResult:
    alloy_system: list[str]
    composition: str
    diagram_type: str
    figure: matplotlib.figure.Figure
    axis: Any = None
    strategy: Any = None

    def to_png_bytes(self) -> bytes:
        buffer = io.BytesIO()
        self.figure.savefig(
            buffer,
            format="png",
            dpi=300,
            bbox_inches="tight",
        )
        buffer.seek(0)
        return buffer.getvalue()


def run_phase_diagram_prediction(
    alloy_system: list[str],
    tdb_dir: str | Path,
    temperature: float | None = None,
    include_intermetallics: bool = True,
    ternary_order: int = 0,
    temperature_min: float = 300,
    temperature_max: float = 3000,
    temperature_step: float = 10,
    composition_step: float | None = None,
) -> PhaseDiagramResult:
    """
    Adapter for binary and ternary phase-diagram plotting.

    Binary:
        alloy_system length = 2
        returns T-x phase diagram

    Ternary:
        alloy_system length = 3
        returns isothermal ternary phase diagram
    """

    if len(alloy_system) not in [2, 3]:
        raise ValueError(
            "Phase diagram plotting currently supports only binary or ternary systems."
        )

    composition = "-".join(alloy_system)

    if len(alloy_system) == 2:
        fig, ax = generate_binary_phase_diagram(
            composition=composition,
            tdb_dir=tdb_dir,
            include_intermetallics=include_intermetallics,
            temperature_min=temperature_min,
            temperature_max=temperature_max,
            temperature_step=temperature_step,
            composition_step=composition_step or 0.02,
        )

        return PhaseDiagramResult(
            alloy_system=alloy_system,
            composition=composition,
            diagram_type="binary",
            figure=fig,
            axis=ax,
            strategy=None,
        )

    if temperature is None:
        raise ValueError(
            "temperature must be provided for ternary phase diagrams."
        )

    fig, ax, strategy = generate_ternary_phase_diagram(
        composition=composition,
        temperature=temperature,
        tdb_dir=tdb_dir,
        include_intermetallics=include_intermetallics,
        order=ternary_order,
        composition_step=composition_step or 0.015,
    )

    return PhaseDiagramResult(
        alloy_system=alloy_system,
        composition=composition,
        diagram_type="ternary",
        figure=fig,
        axis=ax,
        strategy=strategy,
    )