from pathlib import Path
import io

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from pycalphad import Database, equilibrium
from pycalphad import variables as v


def _assign_phase_instance_labels(split_list):
    """
    If the same phase appears more than once, assign instance labels:
        BCC_A2 -> BCC_A2 #1
        BCC_A2 -> BCC_A2 #2

    This is needed for miscibility gaps / phase splitting where two phases
    have the same crystallographic label but different compositions.
    """
    phase_counts = {}

    for entry in split_list:
        phase = entry["phase"]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    running_counts = {}

    for entry in split_list:
        phase = entry["phase"]
        running_counts[phase] = running_counts.get(phase, 0) + 1

        if phase_counts[phase] > 1:
            entry["phase_instance"] = f"{phase} #{running_counts[phase]}"
        else:
            entry["phase_instance"] = phase

    return split_list


def _clean_phase_name(phase):
    if phase is None or pd.isna(phase):
        return None

    phase = str(phase)

    if " #" in phase:
        base, instance = phase.split(" #")
        clean_base = base.split(".")[-1].split("_")[0]
        return f"{clean_base} #{instance}"

    return phase.split(".")[-1].split("_")[0]


def _format_composition_label(elements, mol):
    parts = []
    for el, x in zip(elements, mol):
        parts.append(f"{el}$_{{{x:.2f}}}$")
    return "".join(parts)


def _extract_phase_rows(equi, elements, mol):
    """
    Convert one equilibrium result into a structured row.

    Returns a list of dictionaries:
    [
        {
            "phase": ...,
            "phase_fraction": ...,
            "phase_composition": np.array([...])
        },
        ...
    ]
    """
    phase_info = np.squeeze(np.array(equi.Phase))
    phase_compositions = np.squeeze(np.array(equi.X))
    phase_fractions = np.squeeze(np.array(equi.NP))

    phase_info = np.asarray(phase_info, dtype=object).ravel()
    phase_fractions = np.asarray(phase_fractions, dtype=float).ravel()

    # phase_compositions is typically (n_vertices, n_components)
    phase_compositions = np.asarray(phase_compositions)

    rows = []

    for i, phase in enumerate(phase_info):
        if phase is None or pd.isna(phase) or str(phase).strip() == "":
            continue

        frac = float(phase_fractions[i]) if i < len(phase_fractions) else np.nan
        if np.isnan(frac) or frac <= 0:
            continue

        if phase_compositions.ndim == 2 and i < phase_compositions.shape[0]:
            comp_vec = np.asarray(phase_compositions[i], dtype=float)
        else:
            comp_vec = np.full(len(elements), np.nan)

        rows.append(
            {
                "phase": str(phase),
                "phase_fraction": frac,
                "phase_composition": comp_vec[: len(elements)],
            }
        )

    return rows


def compute_composition_splitting_data(
    composition: str,
    mols: list[list[float]],
    temperature: float,
    tdb_dir: str | Path,
):
    """
    Compute equilibrium phase splitting for a list of alloy compositions
    at one fixed temperature.

    Returns
    -------
    pd.DataFrame
        One row per input alloy composition, with a list-valued column
        containing the predicted phase information.
    """
    tdb_dir = Path(tdb_dir)
    tdb_path = tdb_dir / f"{composition}.tdb"

    if not tdb_path.exists():
        raise FileNotFoundError(f"TDB file not found: {tdb_path}")

    dbf = Database(str(tdb_path))

    elements = composition.split("-")
    real_components = [el.upper() for el in elements]
    comps = real_components + ["VA"]
    phases = list(dbf.phases.keys())

    records = []

    for mol in mols:
        mol = [float(x) for x in mol]

        if len(mol) != len(elements):
            raise ValueError(
                f"Each composition must have {len(elements)} entries. Got {mol}"
            )

        if not np.isclose(sum(mol), 1.0, atol=1e-4):
            raise ValueError(f"Mole fractions must sum to 1. Got {sum(mol):.4f}")

        independent_components = real_components[:-1]

        conditions = {
            v.X(el): mol[i]
            for i, el in enumerate(independent_components)
        }
        conditions[v.T] = float(temperature)
        conditions[v.P] = 101325

        equi = equilibrium(dbf, comps, phases, conditions)
        
        split_rows = _extract_phase_rows(equi, elements, mol)
        split_rows = _assign_phase_instance_labels(split_rows)

        records.append(
            {
                "input_mol": mol,
                "label": _format_composition_label(elements, mol),
                "splitting": split_rows,
            }
        )

    return pd.DataFrame(records)


def plot_composition_splitting(
    df: pd.DataFrame,
    elements: list[str],
    temperature: float,
):
    """
    Plot composition splitting at one temperature.
    """
    all_phase_instances = []
    for split_list in df["splitting"]:
        for entry in split_list:
            all_phase_instances.append(entry.get("phase_instance", entry["phase"]))
    
    unique_phases = sorted(set(all_phase_instances))

    cmap_phases = plt.get_cmap("Spectral")
    if len(unique_phases) > 1:
        phase_colors = {
            phase: cmap_phases(i / (len(unique_phases) - 1))
            for i, phase in enumerate(unique_phases)
        }
    elif len(unique_phases) == 1:
        phase_colors = {unique_phases[0]: cmap_phases(0.5)}
    else:
        phase_colors = {}

    base_element_colors = [
        "#a1c9f4",
        "#ffb482",
        "#8de5a1",
        "#ff9f9b",
        "#d0bbff",
        "#debb9b",
    ]
    element_colors = {
        elem: base_element_colors[i % len(base_element_colors)]
        for i, elem in enumerate(elements)
    }

    fig, ax = plt.subplots(figsize=(9.5, max(3.5, 0.6 * len(df))))

    n_alloys = len(df)
    y_positions = np.arange(n_alloys) * 0.4
    bar_height = 0.15

    y_labels = []
    y_ticks = []

    for i in range(n_alloys):
        row = df.iloc[i]
        y_labels.append(row["label"])
        y_ticks.append(y_positions[i])

        left_phase = 0.0
        left_elem = 0.0

        y_phase = y_positions[i] + bar_height / 2 + 0.005
        y_elem = y_positions[i] - bar_height / 2 - 0.005

        split_list = row["splitting"]

        for phase_entry in split_list:
            phase = phase_entry.get("phase_instance", phase_entry["phase"])
            phase_frac = float(phase_entry["phase_fraction"])
            comp_vec = np.asarray(phase_entry["phase_composition"], dtype=float)

            if left_phase > 0:
                ax.plot(
                    [left_phase, left_phase],
                    [y_elem - bar_height / 2, y_phase + bar_height / 2],
                    color="black",
                    linewidth=2,
                    zorder=5,
                )

            ax.barh(
                y_phase,
                phase_frac,
                left=left_phase,
                height=bar_height,
                color=phase_colors.get(phase, "lightgray"),
                edgecolor="black",
                linewidth=0.8,
                alpha=0.75,
            )

            for elem, x_in_phase in zip(elements, comp_vec):
                if np.isnan(x_in_phase):
                    continue

                x_total = x_in_phase * phase_frac

                if x_total > 0:
                    ax.barh(
                        y_elem,
                        x_total,
                        left=left_elem,
                        height=bar_height,
                        color=element_colors[elem],
                        edgecolor="black",
                        linewidth=0.5,
                        alpha=0.75,
                    )

                    perc = int(round(x_in_phase * 100))
                    if x_total > 0.03 and perc > 0:
                        ax.text(
                            left_elem + x_total / 2,
                            y_elem,
                            f"{perc}",
                            ha="center",
                            va="center",
                            fontsize=8,
                            color="black",
                        )

                    left_elem += x_total

            left_phase += phase_frac

        ax.plot([0, 0], [y_elem - bar_height / 2, y_phase + bar_height / 2],
                color="black", linewidth=2, zorder=5)
        ax.plot([1, 1], [y_elem - bar_height / 2, y_phase + bar_height / 2],
                color="black", linewidth=2, zorder=5)

    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Phase fraction")
    ax.set_xlim(0, 1)
    ax.set_title(f"Composition splitting at {temperature:.0f} K")

    legend_elements_phase = [
        Patch(
            facecolor=phase_colors[p],
            edgecolor="black",
            label=_clean_phase_name(p),
            linewidth=0.5,
        )
        for p in unique_phases
    ]

    legend_elements_elem = [
        Patch(
            facecolor=element_colors[e],
            edgecolor="black",
            label=e,
            linewidth=0.5,
        )
        for e in elements
    ]

    if legend_elements_phase:
        leg1 = ax.legend(
            handles=legend_elements_phase,
            title="Phases",
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
            frameon=False,
        )
        ax.add_artist(leg1)

    ax.legend(
        handles=legend_elements_elem,
        title="Elements",
        bbox_to_anchor=(1.02, 0.4),
        loc="upper left",
        frameon=False,
    )

    fig.tight_layout()
    return fig


def generate_composition_splitting_profile(
    composition: str,
    mols: list[list[float]],
    temperature: float,
    tdb_dir: str | Path,
):
    """
    Convenience wrapper returning both data and figure.
    """
    df = compute_composition_splitting_data(
        composition=composition,
        mols=mols,
        temperature=temperature,
        tdb_dir=tdb_dir,
    )

    fig = plot_composition_splitting(
        df=df,
        elements=composition.split("-"),
        temperature=temperature,
    )

    return df, fig