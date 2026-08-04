from pathlib import Path

from pycalphad import Database, equilibrium
from pycalphad import variables as v

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.energy_above_hull import (
    calculate_homogeneous_bcc_gibbs,
    energy_above_hull_mev,
    plot_bcc_energy_above_hull,
)


def _rename_duplicate_phases(row):
    counts = {}
    new_row = []

    for item in row:
        if item is None:
            new_row.append(None)
            continue

        item = str(item)
        counts[item] = counts.get(item, 0) + 1

        if counts[item] > 1:
            new_row.append(f"{counts[item]}.{item}")
        else:
            new_row.append(item)

    return new_row


def _clean_phase_label(label):
    base_name = str(label).split(".")[-1]
    base_name = base_name.split("_")[0]
    return base_name


def generate_phase_fraction_temperature_profile(
    composition: str,
    mol_ratio: list[float],
    input_file_path: str | Path,
    temp_range: tuple[float, float, float],
):
    """
    Compute phase fractions as a function of temperature for one composition.

    Parameters
    ----------
    composition
        Alloy system label, e.g. "Cr-Mo-Nb-Ta".

    mol_ratio
        Full composition vector in the same order as composition.split("-").
        Example: [0.25, 0.25, 0.25, 0.25].

    input_file_path
        Directory containing TDB files.

    temp_range
        pycalphad temperature range, e.g. (300, 2500, 50).

    Returns
    -------
    result_df : pandas.DataFrame
        Phase fractions vs temperature.

    fig : matplotlib.figure.Figure
        Horizontal stacked phase-fraction plot.
    """

    input_file_path = Path(input_file_path)

    tdb_path = input_file_path / f"{composition}.tdb"
    if not tdb_path.exists():
        raise FileNotFoundError(f"TDB file not found: {tdb_path}")

    dbf = Database(str(tdb_path))

    elements = composition.split("-")
    real_components = [el.upper() for el in elements]
    comps = real_components + ["VA"]
    phases = list(dbf.phases.keys())

    if len(mol_ratio) != len(real_components):
        raise ValueError(
            f"mol_ratio length must match number of elements. "
            f"Got mol_ratio={mol_ratio}, elements={elements}"
        )

    if not np.isclose(sum(mol_ratio), 1.0):
        raise ValueError(
            f"mol_ratio must sum to 1. Got sum={sum(mol_ratio)}"
        )

    independent_components = real_components[:-1]

    conditions = {
        v.X(el): float(mol_ratio[i])
        for i, el in enumerate(independent_components)
    }

    conditions[v.T] = tuple(temp_range)
    conditions[v.P] = 101325

    equi = equilibrium(
        dbf,
        comps,
        phases,
        conditions,
    )

    equilibrium_gibbs = np.squeeze(np.asarray(equi.GM, dtype=float))

    fractions = np.round(
        np.squeeze(np.array(equi.NP)).astype(float),
        3,
    )

    phase_names = np.squeeze(np.array(equi.Phase))
    temperatures = np.squeeze(np.array(equi.T))

    temperatures = np.asarray(temperatures, dtype=float)
    fractions = np.asarray(fractions, dtype=float)
    phase_names = np.asarray(phase_names, dtype=object)

    fractions = np.nan_to_num(fractions, nan=0.0)

    phase_names = np.where(
        (phase_names == "")
        | (phase_names == "nan")
        | (phase_names == None),
        None,
        phase_names,
    )

    order_t = np.argsort(temperatures)
    temperatures = temperatures[order_t]
    fractions = fractions[order_t]
    phase_names = phase_names[order_t]
    equilibrium_gibbs = np.atleast_1d(equilibrium_gibbs)[order_t]

    bcc_gibbs = calculate_homogeneous_bcc_gibbs(
        database=dbf,
        components=real_components,
        mols=[mol_ratio],
        temperatures=temperatures,
    )[:, 0]
    bcc_energy_above_hull = energy_above_hull_mev(
        bcc_gibbs,
        equilibrium_gibbs,
    )
    energy_figure, threshold_temperature, stable_temperature = (
        plot_bcc_energy_above_hull(temperatures, bcc_energy_above_hull)
    )
    energy_df = pd.DataFrame(
        {
            "temperature": temperatures,
            "BCC_A2 energy above hull (meV/atom)": bcc_energy_above_hull,
        }
    )

    processed_rows = [
        _rename_duplicate_phases(row)
        for row in phase_names
    ]

    phase_names = np.array(processed_rows, dtype=object)

    unique_phases = sorted(
        {
            phase
            for row in processed_rows
            for phase in row
            if phase is not None
        }
    )

    n_temps, n_vertices = fractions.shape
    n_phases = len(unique_phases)

    phase_index = {
        phase: i
        for i, phase in enumerate(unique_phases)
    }

    phase_fraction_matrix = np.zeros(
        (n_temps, n_phases),
        dtype=float,
    )

    for i in range(n_temps):
        for j in range(n_vertices):
            phase = phase_names[i, j]

            if phase is not None:
                phase_fraction_matrix[i, phase_index[phase]] += fractions[i, j]

    row_sum = phase_fraction_matrix.sum(axis=1, keepdims=True)
    nonzero = row_sum.squeeze() > 0

    phase_fraction_matrix[nonzero] = (
        phase_fraction_matrix[nonzero] / row_sum[nonzero]
    )

    phase_order = np.argsort(
        phase_fraction_matrix.mean(axis=0)
    )[::-1]

    phase_fraction_matrix = phase_fraction_matrix[:, phase_order]
    phases_ordered = [unique_phases[i] for i in phase_order]

    result_df = pd.DataFrame(
        phase_fraction_matrix,
        columns=phases_ordered,
    )

    result_df.insert(0, "temperature", temperatures)

    fig, ax = plt.subplots(figsize=(5, 5))

    cmap = plt.get_cmap("Spectral_r", len(phases_ordered))
    colors = [cmap(i) for i in range(len(phases_ordered))]

    if len(temperatures) > 1:
        step = np.min(np.diff(np.unique(temperatures)))
        width = 0.6 * step
    else:
        width = 0.5

    left = np.zeros(len(temperatures))

    for i, phase in enumerate(phases_ordered):
        ax.barh(
            temperatures,
            phase_fraction_matrix[:, i],
            left=left,
            height=width,
            color=colors[i],
            edgecolor="black",
            linewidth=0.6,
            alpha=0.75,
            label=phase,
        )

        left += phase_fraction_matrix[:, i]

    ax.set_xlabel("Phase fraction")
    ax.set_ylabel("Temperature (K)")
    ax.set_xlim(0, 1)

    if len(temp_range) == 3:
        ax.set_yticks(np.arange(*temp_range))

    handles, labels = ax.get_legend_handles_labels()

    clean_labels = [
        _clean_phase_label(label)
        for label in labels
    ]

    ax.legend(
        handles,
        clean_labels,
        bbox_to_anchor=(0.85, 1.1),
        ncol=max(1, len(clean_labels)),
        frameon=False,
    )

    fig.subplots_adjust(
        left=0.15,
        right=0.95,
        top=0.9,
        bottom=0.1,
    )

    return (
        result_df,
        fig,
        energy_df,
        energy_figure,
        threshold_temperature,
        stable_temperature,
    )
