from pathlib import Path
import sys
import traceback

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports, TDB_DIR
from alloy_web.icons import brand_favicon, page_title
from alloy_web.ui import element_selector, show_input_summary


ensure_project_imports()

from alloy_web.adapters.alloy_summary_adapter import run_alloy_system_summary
from alloy_web.adapters.experimental_adapter import (
    DEFAULT_CITATION_PATH,
    ExperimentalEvidence,
    load_experimental_evidence,
)
from alloy_assistant.src.database import DEFAULT_DATABASE_PATH


INTERACTION_DATA_PATH = (
    ROOT
    / "external"
    / "Rapid_Phase_Field_Prediction"
    / "input"
    / "spinodal"
    / "binary_interactions.json"
)


st.set_page_config(
    page_title="Alloy System Summary",
    page_icon=brand_favicon(),
    layout="wide",
)


def _source_version() -> int:
    paths = [INTERACTION_DATA_PATH, *TDB_DIR.glob("*.tdb")]
    return max(path.stat().st_mtime_ns for path in paths if path.exists())


@st.cache_data(show_spinner=False)
def _cached_summary(
    alloy_system: tuple[str, ...],
    reference_temperature: float,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    source_version: int,
):
    del source_version
    return run_alloy_system_summary(
        alloy_system=list(alloy_system),
        reference_temperature=reference_temperature,
        temperature_min=temperature_min,
        temperature_max=temperature_max,
        temperature_step=temperature_step,
        tdb_dir=TDB_DIR,
        interaction_data_path=INTERACTION_DATA_PATH,
        miscibility_threshold=0.99,
        max_sample_points=400,
    )


@st.cache_data(show_spinner=False)
def _cached_experimental_evidence(
    alloy_system: tuple[str, ...],
    database_version: int,
    citation_version: int,
) -> ExperimentalEvidence:
    del database_version, citation_version
    return load_experimental_evidence(alloy_system)


def _download_table(label: str, data: pd.DataFrame, file_name: str, key: str):
    st.download_button(
        label,
        data=data.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        key=key,
    )


def _plot_miscibility_temperatures(
    data: pd.DataFrame,
    temperature_min: float,
    temperature_max: float,
    reference_temperature: float,
):
    plot_data = data.dropna(subset=["Miscibility temperature value (K)"]).copy()
    plot_data = plot_data[
        plot_data["Miscibility temperature value (K)"].between(
            temperature_min, temperature_max
        )
    ]
    if plot_data.empty:
        return None

    phase_colors = {
        "BCC_A2": "#4477AA",
        "FCC_A1": "#CC6677",
        "HCP_A3": "#228833",
    }
    orders = sorted(plot_data["Order"].unique())
    order_names = {2: "Binary", 3: "Ternary", 4: "Quaternary", 5: "Quinary"}
    group_sizes = [len(plot_data[plot_data["Order"] == order]) for order in orders]
    figure_height = max(4.2, 0.48 * sum(group_sizes) + 1.4 * len(orders))
    fig, axes = plt.subplots(
        len(orders),
        1,
        figsize=(8.2, figure_height),
        sharex=True,
        gridspec_kw={"height_ratios": group_sizes},
    )
    axes = np.atleast_1d(axes)

    for ax, order in zip(axes, orders):
        group = plot_data[plot_data["Order"] == order].sort_values("Subsystem")
        y_positions = np.arange(len(group))
        values = group["Miscibility temperature value (K)"].to_numpy(dtype=float)
        colors = [
            phase_colors.get(phase, "#999999")
            for phase in group["Solid solution at transition"]
        ]
        ax.barh(
            y_positions,
            values - temperature_min,
            left=temperature_min,
            color=colors,
            height=0.62,
        )
        ax.set_yticks(y_positions, group["Subsystem"])
        ax.invert_yaxis()
        ax.set_title(
            f"{order_names.get(order, f'{order}-component')} systems",
            loc="left",
            fontsize=10,
            fontweight="bold",
        )
        ax.grid(axis="x", alpha=0.18)
        ax.spines[["top", "right", "left"]].set_visible(False)
        for y_position, value in zip(y_positions, values):
            ax.text(
                min(value + 18, temperature_max - 5),
                y_position,
                f"{value:.0f} K",
                va="center",
                ha="left" if value < temperature_max - 100 else "right",
                fontsize=8,
            )
        if temperature_min <= reference_temperature <= temperature_max:
            ax.axvline(
                reference_temperature,
                color="#333333",
                linestyle="--",
                linewidth=1.0,
                alpha=0.65,
            )

    axes[-1].set_xlim(temperature_min, temperature_max)
    axes[-1].set_xlabel("Miscibility temperature (K)")
    present_phases = [
        phase
        for phase in phase_colors
        if phase in set(plot_data["Solid solution at transition"].dropna())
    ]
    legend_handles = [
        Patch(color=phase_colors[phase], label=phase) for phase in present_phases
    ]
    if legend_handles:
        fig.legend(handles=legend_handles, loc="upper right", frameon=False, ncol=3)
    fig.tight_layout()
    return fig


def _plot_interaction_heatmap(matrix: pd.DataFrame, lattice: str):
    values = matrix.to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    color_limit = max(float(np.max(np.abs(finite_values))), 1e-12)
    cmap = plt.get_cmap("coolwarm").copy()
    cmap.set_bad("#eeeeee")

    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    image = ax.imshow(
        np.ma.masked_invalid(values),
        cmap=cmap,
        norm=Normalize(vmin=-color_limit, vmax=color_limit),
    )
    ax.set_xticks(range(len(matrix.columns)), matrix.columns)
    ax.set_yticks(range(len(matrix.index)), matrix.index)
    ax.set_title(f"{lattice} binary interaction parameters")

    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values[row, column]
            if np.isfinite(value):
                text_color = "white" if abs(value) > 0.55 * color_limit else "black"
                ax.text(
                    column,
                    row,
                    f"{value:.3f}",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=9,
                )

    colorbar = fig.colorbar(image, ax=ax, shrink=0.82)
    colorbar.set_label("Ω (eV/atom)")
    fig.tight_layout()
    return fig


page_title("Alloy System Summary", "summary")
st.markdown(
    "A compact thermodynamic overview of an alloy system and all of its equimolar subsystems."
)

with st.container(border=True):
    st.markdown("#### What counts as miscible?")
    st.caption(
        "A composition is miscible when at least 99% of it forms one solid solution: "
        "BCC_A2, FCC_A1, or HCP_A3. If that structure separates into two compositions—for "
        "example, two BCC_A2 solutions—it is treated as multiphase rather than miscible."
    )


with st.sidebar:
    st.header("Alloy summary inputs")

    alloy_system = element_selector(
        "Alloy system",
        default=["Cr", "Ta", "Ti", "W"],
        min_elements=2,
        max_elements=5,
    )

    reference_temperature = st.number_input(
        "Reference temperature / K",
        min_value=100,
        max_value=5000,
        value=1500,
        step=50,
    )

    with st.expander("Temperature search"):
        temperature_min = st.number_input(
            "Minimum temperature / K",
            min_value=100,
            max_value=4000,
            value=300,
            step=50,
        )
        temperature_max = st.number_input(
            "Maximum temperature / K",
            min_value=200,
            max_value=5000,
            value=3000,
            step=50,
        )
        temperature_step = st.number_input(
            "Coarse step / K",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
            help="Detected transitions are refined to approximately 1 K.",
        )

    run_button = st.button("Summarize alloy system", type="primary")


input_signature = (
    tuple(alloy_system),
    float(reference_temperature),
    float(temperature_min),
    float(temperature_max),
    float(temperature_step),
)

left, right = st.columns([1, 2.2])
with left:
    show_input_summary(
        {
            "alloy_system": alloy_system,
            "reference_temperature": float(reference_temperature),
            "temperature_range": [float(temperature_min), float(temperature_max)],
            "temperature_step": float(temperature_step),
        },
        title="Summary inputs",
    )


if run_button:
    try:
        with st.spinner("Building alloy-system summary..."):
            summary = _cached_summary(
                *input_signature,
                source_version=_source_version(),
            )
        st.session_state["alloy_summary_result"] = summary
        st.session_state["alloy_summary_signature"] = input_signature
    except Exception as exc:
        st.error("Alloy-system summary failed.")
        st.code(str(exc))
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())


summary = None
if st.session_state.get("alloy_summary_signature") == input_signature:
    summary = st.session_state.get("alloy_summary_result")


if summary is not None:
    reference_column = f"Miscible at {summary.reference_temperature:.0f} K"
    full_system_label = "-".join(summary.alloy_system)
    full_row = summary.subsystems.loc[
        summary.subsystems["Subsystem"] == full_system_label
    ].iloc[0]
    full_transition_phase = full_row["Solid solution at transition"]
    if pd.isna(full_transition_phase):
        full_transition_phase = "No single solid solution"
    computable_subsystems = summary.subsystems[reference_column].notna().sum()
    miscible_subsystems = (summary.subsystems[reference_column] == True).sum()

    experimental_evidence = None
    experimental_error = None
    try:
        experimental_evidence = _cached_experimental_evidence(
            tuple(summary.alloy_system),
            database_version=(
                DEFAULT_DATABASE_PATH.stat().st_mtime_ns
                if DEFAULT_DATABASE_PATH.is_file()
                else 0
            ),
            citation_version=DEFAULT_CITATION_PATH.stat().st_mtime_ns,
        )
    except Exception as exc:
        experimental_error = str(exc)

    with right:
        st.markdown(f"## {' – '.join(summary.alloy_system)}")
        st.caption(
            f"{summary.equilibrium_calculations:,} equilibrium calculations in "
            f"{summary.elapsed_seconds:.2f} seconds · {summary.sample_points} compositions"
        )

    metric_columns = st.columns(5)
    with metric_columns[0]:
        st.metric(
            "Miscible region",
            f"{summary.miscible_percentage:.1f}%",
            help=f"{summary.miscible_sample_points} of {summary.evaluated_sample_points} evaluated compositions.",
        )
    with metric_columns[1]:
        st.metric(
            "Miscible temperature",
            full_row["Miscibility temperature"],
            delta=full_transition_phase,
            delta_color="off",
        )
    with metric_columns[2]:
        st.metric(
            f"Miscible subsystems at {summary.reference_temperature:.0f} K",
            f"{miscible_subsystems} / {computable_subsystems}",
            help="Equimolar subsystems satisfying the single-solid-solution definition.",
        )
    with metric_columns[3]:
        st.metric("Considered intermetallics", f"{len(summary.intermetallics)}")
    with metric_columns[4]:
        st.metric("Runtime", f"{summary.elapsed_seconds:.2f} s")

    tab_names = ["Overview", "Intermetallics", "Binary interactions", "Downloads"]
    has_experimental_evidence = (
        experimental_evidence is not None
        and not experimental_evidence.observations.empty
    )
    if has_experimental_evidence:
        tab_names.append(
            f"Experimental evidence ({len(experimental_evidence.observations)})"
        )
    tabs = st.tabs(tab_names)
    overview_tab, intermetallic_tab, interaction_tab, downloads_tab = tabs[:4]
    experimental_tab = tabs[4] if has_experimental_evidence else None

    with overview_tab:
        chart_column, phase_column = st.columns([1.6, 1])
        with chart_column:
            st.markdown("#### Equimolar subsystem miscibility temperatures")
            temperature_figure = _plot_miscibility_temperatures(
                summary.subsystems,
                temperature_min=float(temperature_min),
                temperature_max=float(temperature_max),
                reference_temperature=summary.reference_temperature,
            )
            if temperature_figure is None:
                st.info("No miscibility transition was found in the selected range.")
            else:
                st.pyplot(temperature_figure, width="stretch")
                plt.close(temperature_figure)

        with phase_column:
            st.markdown(
                f"#### Percentage miscible region (PMR) at {summary.reference_temperature:.0f} K"
            )
            if summary.sample_phase_breakdown.empty:
                st.info("No sampled point met the single-solid-solution definition.")
            else:
                for phase_row in summary.sample_phase_breakdown.itertuples(index=False):
                    with st.container(border=True):
                        st.metric(
                            phase_row[0],
                            f"{phase_row[2]:.1f}%",
                            delta=f"{phase_row[1]} compositions",
                            delta_color="off",
                        )

        st.markdown("#### Subsystem details")
        subsystem_display = summary.subsystems.drop(
            columns=["Miscibility temperature value (K)"],
            errors="ignore",
        )
        st.dataframe(
            subsystem_display,
            width="stretch",
            hide_index=True,
            column_config={
                reference_column: st.column_config.CheckboxColumn(),
            },
        )

    with intermetallic_tab:
        st.markdown("#### Considered intermetallics from the full-system TDB")
        st.caption(
            "Only phases whose TDB name ends in _MP are listed. Formation energies are "
            "the reference-subtracted constants encoded in the generated TDB. For each "
            "reduced composition, only the lowest-energy entry is retained."
        )
        if summary.intermetallics.empty:
            st.info("No _MP phases were found in the full-system TDB.")
        else:
            for subsystem, group in summary.intermetallics.groupby("Subsystem", sort=True):
                st.markdown(f"##### {subsystem}")
                st.dataframe(
                    group.drop(columns=["Subsystem"]),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Formation energy (eV/atom)": st.column_config.NumberColumn(format="%.4f"),
                    },
                )

    with interaction_tab:
        st.markdown("#### Binary regular-solution interactions")
        st.caption(
            "Ω values come from the spinodal interaction dataset. Positive values favor "
            "demixing; negative values favor mixing in this regular-solution convention."
        )
        lattice = st.selectbox("Heatmap lattice", ["BCC", "FCC", "HCP"])
        interaction_column = f"{lattice} (eV/atom)"
        matrix = pd.DataFrame(
            np.nan,
            index=summary.alloy_system,
            columns=summary.alloy_system,
        )
        for element in summary.alloy_system:
            matrix.loc[element, element] = 0.0
        for _, row in summary.binary_interactions.iterrows():
            a, b = row["Pair"].split("-")
            matrix.loc[a, b] = row[interaction_column]
            matrix.loc[b, a] = row[interaction_column]
        interaction_figure = _plot_interaction_heatmap(matrix, lattice)
        st.pyplot(interaction_figure, width="stretch")
        plt.close(interaction_figure)

        with st.expander("Interaction values"):
            st.dataframe(
                summary.binary_interactions,
                width="stretch",
                hide_index=True,
                column_config={
                    column: st.column_config.NumberColumn(format="%.3f")
                    for column in summary.binary_interactions.columns
                    if column != "Pair"
                },
            )

        with st.expander("TDB Redlich–Kister parameters"):
            st.caption(
                "The full-system TDB values are shown separately by solid-solution phase and order."
            )
            st.dataframe(
                summary.tdb_interactions,
                width="stretch",
                hide_index=True,
                column_config={
                    "L (J/mol)": st.column_config.NumberColumn(format="%.3f"),
                    "L (eV/atom)": st.column_config.NumberColumn(format="%.3f"),
                },
            )

    with downloads_tab:
        st.markdown("#### Download report data")
        download_columns = st.columns(3)
        with download_columns[0]:
            _download_table(
                "Subsystems CSV",
                summary.subsystems,
                f"{full_system_label}_subsystems.csv",
                "summary_subsystems_csv",
            )
        with download_columns[1]:
            _download_table(
                "Intermetallics CSV",
                summary.intermetallics,
                f"{full_system_label}_intermetallics.csv",
                "summary_intermetallics_csv",
            )
        with download_columns[2]:
            _download_table(
                "Interactions CSV",
                summary.binary_interactions,
                f"{full_system_label}_binary_interactions.csv",
                "summary_interactions_csv",
            )

    if experimental_tab is not None:
        with experimental_tab:
            st.markdown("#### Published experimental evidence")

            evidence_metrics = st.columns(3)
            with evidence_metrics[0]:
                st.metric(
                    "Experimental records",
                    len(experimental_evidence.observations),
                )
            with evidence_metrics[1]:
                st.metric(
                    "Compositions",
                    experimental_evidence.observations["Composition"].nunique(),
                )
            with evidence_metrics[2]:
                st.metric("Publications", len(experimental_evidence.citations))

            st.dataframe(
                experimental_evidence.observations,
                width="stretch",
                hide_index=True,
                column_config={
                    "Processing temperature (K)": st.column_config.NumberColumn(
                        format="%.0f"
                    ),
                },
            )

            st.markdown("##### Sources")
            for citation in experimental_evidence.citations.itertuples(index=False):
                st.markdown(f"**{citation[0]}** {citation[1]}")

    if experimental_error:
        with st.expander("Experimental evidence unavailable"):
            st.caption(
                "The thermodynamic summary is unaffected; the experimental evidence "
                "source could not be validated."
            )
            st.code(experimental_error)
