from dataclasses import dataclass
from pathlib import Path
import io
import pandas as pd
import matplotlib.figure

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_predictor import (
    load_interaction_data,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_analysis import (
    compute_spinodal_vs_temperature,
    estimate_spinodal_temperature,
    compute_mode_at_temperature,
    plot_eigenvalues_vs_temperature,
    plot_mode_bar,
    interpret_mode,
)


@dataclass
class SpinodalPageResult:
    """Spinodal eigenvalue spectrum, soft mode, plots, and interpretation.

    Temperatures are in kelvin. ``spinodal_temperature`` is ``None`` if no
    zero crossing is found on the requested temperature grid.

    Attributes:
        alloy_system: Element symbols in input order.
        mol_ratio: Mole fractions paired with ``alloy_system``.
        lattice: Evaluated solid-solution lattice identifier.
        spectrum_data: Temperature-dependent Hessian eigenvalue table.
        spinodal_temperature: Estimated minimum-eigenvalue crossing in kelvin.
        mode_temperature: Temperature in kelvin used for the soft mode.
        mode_result: Eigenvalues, eigenvectors, and selected mode data.
        eigenvalue_figure: Eigenvalue-spectrum plot.
        mode_figure: Element-resolved soft-mode plot.
        interpretation: Sign-separated soft-mode interpretation.
    """
    alloy_system: list[str]
    mol_ratio: list[float]
    lattice: str
    spectrum_data: pd.DataFrame
    spinodal_temperature: float | None
    mode_temperature: float
    mode_result: dict
    eigenvalue_figure: matplotlib.figure.Figure
    mode_figure: matplotlib.figure.Figure
    interpretation: dict

    def to_csv_bytes(self) -> bytes:
        return self.spectrum_data.to_csv(index=False).encode("utf-8")

    def fig_to_png_bytes(self, fig) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        buf.seek(0)
        return buf.getvalue()


def run_spinodal_analysis(
    alloy_system: list[str],
    mol_ratio: list[float],
    lattice: str,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    mode_temperature: float,
    interaction_data_path: str | Path,
) -> SpinodalPageResult:
    """Calculate the constrained-composition spinodal spectrum and a soft mode.

    Args:
        alloy_system: Element symbols paired with ``mol_ratio``.
        mol_ratio: Mole fractions that sum to one.
        lattice: Solid-solution lattice identifier, such as ``"BCC"``.
        temperature_min: Inclusive lower grid bound in kelvin.
        temperature_max: Upper grid bound in kelvin.
        temperature_step: Grid spacing in kelvin.
        mode_temperature: Temperature in kelvin at which to evaluate the soft
            eigenmode.
        interaction_data_path: JSON file containing binary interaction models.

    Returns:
        The eigenvalue table, estimated crossing temperature, soft-mode data,
        figures, and a sign-separated interpretation of the mode.

    Raises:
        ValueError: If the element and composition lengths differ or the mole
            fractions do not sum to one.
        FileNotFoundError: If the interaction data file does not exist.
    """

    if len(alloy_system) != len(mol_ratio):
        raise ValueError("Number of elements and mole fractions must match.")

    if not abs(sum(mol_ratio) - 1.0) < 1e-6:
        raise ValueError(f"Mole fractions must sum to 1. Current sum = {sum(mol_ratio):.6f}")

    interaction_data = load_interaction_data(interaction_data_path)

    spectrum_df = compute_spinodal_vs_temperature(
        composition=alloy_system,
        mol_ratio=mol_ratio,
        lattice=lattice,
        interaction_data=interaction_data,
        temperature_min=temperature_min,
        temperature_max=temperature_max,
        temperature_step=temperature_step,
    )

    spinodal_temperature = estimate_spinodal_temperature(spectrum_df)

    mode_result = compute_mode_at_temperature(
        composition=alloy_system,
        mol_ratio=mol_ratio,
        lattice=lattice,
        interaction_data=interaction_data,
        temperature=mode_temperature,
    )

    eig_fig = plot_eigenvalues_vs_temperature(
        spectrum_df,
        spinodal_temperature=spinodal_temperature,
    )

    mode_fig = plot_mode_bar(
        composition=alloy_system,
        mode=mode_result["mode"],
        temperature=mode_temperature,
    )

    interpretation = interpret_mode(
        composition=alloy_system,
        mode=mode_result["mode"],
    )

    return SpinodalPageResult(
        alloy_system=alloy_system,
        mol_ratio=mol_ratio,
        lattice=lattice,
        spectrum_data=spectrum_df,
        spinodal_temperature=spinodal_temperature,
        mode_temperature=mode_temperature,
        mode_result=mode_result,
        eigenvalue_figure=eig_fig,
        mode_figure=mode_fig,
        interpretation=interpretation,
    )
