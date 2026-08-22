from dataclasses import dataclass
from pathlib import Path
from typing import Any
import io

import pandas as pd
import matplotlib.figure

from alloy_web.adapters.alloy_summary_adapter import resolve_tdb_for_system
from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.temperature_profile_per_composition import generate_phase_fraction_temperature_profile
from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.composition_profile_per_temperature import generate_composition_splitting_profile
from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.phase_diagram_plotters import generate_binary_phase_diagram, generate_ternary_phase_diagram


def _reorder(values: list[float], elements: list[str], ordered: list[str]) -> list[float]:
    """Move per-element values onto the element order the TDB file uses."""
    position = {element.upper(): index for index, element in enumerate(elements)}
    return [float(values[position[element.upper()]]) for element in ordered]


@dataclass
class PhaseFractionTemperatureResult:
    """Phase fractions and homogeneous-BCC stability over a temperature grid.

    Temperatures are expressed in kelvin and energy-above-hull values in the
    returned table are expressed in meV/atom. ``metastable_temperature`` and
    ``stable_temperature`` are ``None`` when the corresponding threshold is
    not found on the requested grid.

    Attributes:
        composition: Hyphenated element system in resolved TDB order.
        mol_ratio: Mole fractions reordered to match ``composition``.
        temp_range: ``(minimum, maximum, step)`` in kelvin.
        data: Temperature-dependent phase-fraction table.
        figure: Phase-fraction plot.
        energy_above_hull_data: Homogeneous-BCC energy table in meV/atom.
        energy_above_hull_figure: BCC energy-above-hull plot.
        metastable_temperature: Detected 50 meV/atom threshold in kelvin.
        stable_temperature: Detected zero-energy threshold in kelvin.
    """
    composition: str
    mol_ratio: list[float]
    temp_range: tuple[float, float, float]
    data: pd.DataFrame
    figure: matplotlib.figure.Figure
    energy_above_hull_data: pd.DataFrame
    energy_above_hull_figure: matplotlib.figure.Figure
    metastable_temperature: float | None
    stable_temperature: float | None

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
    """Calculate phase fractions and BCC energy above hull versus temperature.

    Args:
        alloy_system: Element symbols. At least two elements are required.
        mol_ratio: Mole fractions paired positionally with ``alloy_system``.
            Fractions must sum to one.
        temperature_min: Inclusive lower temperature bound in kelvin.
        temperature_max: Upper temperature bound in kelvin.
        temperature_step: Temperature-grid spacing in kelvin.
        tdb_dir: Directory containing RAPTor ``.tdb`` databases.

    Returns:
        Phase-fraction and BCC energy-above-hull tables, figures, and detected
        metastability/stability thresholds.

    Raises:
        ValueError: If the element or composition inputs are inconsistent.
        FileNotFoundError: If no database covers the requested elements.

    Notes:
        The returned element order can follow the matching TDB filename rather
        than the input order. ``result.mol_ratio`` is reordered consistently.
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

    _, ordered_elements = resolve_tdb_for_system(alloy_system, tdb_dir)
    mol_ratio = _reorder(mol_ratio, alloy_system, ordered_elements)
    composition = "-".join(ordered_elements)

    temp_range = (
        float(temperature_min),
        float(temperature_max),
        float(temperature_step),
    )

    (
        data,
        fig,
        energy_data,
        energy_figure,
        metastable_temperature,
        stable_temperature,
    ) = generate_phase_fraction_temperature_profile(
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
        energy_above_hull_data=energy_data,
        energy_above_hull_figure=energy_figure,
        metastable_temperature=metastable_temperature,
        stable_temperature=stable_temperature,
    )

@dataclass
class CompositionSplittingSingleResult:
    """Equilibrium phase compositions at one temperature in kelvin.

    Attributes:
        temperature: Evaluation temperature in kelvin.
        data: Equilibrium phase-composition table.
        figure: Composition-splitting plot.
    """
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
    """Composition-splitting results for one to three temperatures.

    Attributes:
        alloy_system: Elements in resolved TDB order.
        mols: Overall mole-fraction vectors in resolved TDB order.
        results: One result object per requested temperature.
    """
    alloy_system: list[str]
    mols: list[list[float]]
    results: list[CompositionSplittingSingleResult]


def run_composition_splitting_prediction(
    alloy_system: list[str],
    mols: list[list[float]],
    temperatures: list[float],
    tdb_dir: str | Path,
) -> CompositionSplittingResult:
    """Calculate equilibrium composition splitting at selected temperatures.

    Args:
        alloy_system: Element symbols paired with each row in ``mols``.
        mols: Overall compositions; each inner list contains mole fractions in
            ``alloy_system`` order and must satisfy the underlying engine's
            composition constraints.
        temperatures: One to three temperatures in kelvin.
        tdb_dir: Directory containing RAPTor ``.tdb`` databases.

    Returns:
        One table and figure per requested temperature. Element and composition
        order in the result follow the resolved TDB filename.

    Raises:
        ValueError: If no temperature or more than three temperatures are given.
        FileNotFoundError: If no database covers the requested elements.
    """
    if len(temperatures) == 0:
        raise ValueError("Provide at least one temperature.")

    if len(temperatures) > 3:
        raise ValueError("At most 3 temperatures are supported.")

    _, ordered_elements = resolve_tdb_for_system(alloy_system, tdb_dir)
    mols = [_reorder(mol, alloy_system, ordered_elements) for mol in mols]
    composition = "-".join(ordered_elements)

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
        alloy_system=ordered_elements,
        mols=mols,
        results=results,
    )



@dataclass
class PhaseDiagramResult:
    """A binary temperature-composition or isothermal ternary phase diagram.

    Attributes:
        alloy_system: Elements in resolved TDB order.
        composition: Hyphenated version of ``alloy_system``.
        diagram_type: Either ``"binary"`` or ``"ternary"``.
        figure: Generated Matplotlib figure.
        axis: Matplotlib axis used by the plotter.
        strategy: Ternary mapping strategy; ``None`` for binary diagrams.
    """
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
    """Calculate a binary T-x or isothermal ternary phase diagram.

    Args:
        alloy_system: Exactly two elements for a binary diagram or three for a
            ternary diagram.
        tdb_dir: Directory containing RAPTor ``.tdb`` databases.
        temperature: Isothermal temperature in kelvin. Required only for a
            ternary diagram.
        include_intermetallics: Include applicable intermetallic phases when
            ``True``.
        ternary_order: Plotting orientation passed to the ternary strategy.
        temperature_min: Binary diagram lower temperature in kelvin.
        temperature_max: Binary diagram upper temperature in kelvin.
        temperature_step: Binary diagram temperature-grid spacing in kelvin.
        composition_step: Mole-fraction grid spacing. Defaults to ``0.02`` for
            binary and ``0.015`` for ternary calculations.

    Returns:
        The diagram figure, plotting axis, normalized element order, and the
        ternary strategy object when applicable.

    Raises:
        ValueError: If the system order is unsupported or a ternary temperature
            is omitted.
        FileNotFoundError: If no database covers the requested elements.
    """

    if len(alloy_system) not in [2, 3]:
        raise ValueError(
            "Phase diagram plotting currently supports only binary or ternary systems."
        )

    _, alloy_system = resolve_tdb_for_system(alloy_system, tdb_dir)
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
