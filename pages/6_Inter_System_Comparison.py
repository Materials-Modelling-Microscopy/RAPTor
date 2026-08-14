from math import comb
from pathlib import Path
import sys
import traceback

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports, TDB_DIR
from alloy_web.icons import brand_favicon, icon_markup
from alloy_web.ui import element_selector


ensure_project_imports()

from alloy_web.adapters.inter_system_adapter import (
    ACTIVE_PHASE_COUNT,
    EQUIMOLAR_SOLID_SOLUTION_FRACTION,
    METASTABILITY_GAP,
    MEAN_PATH_BURDEN,
    METRICS,
    MISCIBILITY_TEMPERATURE,
    PATH_BURDEN_VARIANCE,
    PMR,
    SPINODAL_TEMPERATURE,
    run_inter_system_comparison,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.pathway_analysis import (
    plot_system_path_burden_landscape,
)


# Matches the precision each metric's `__display` string already uses
# (see alloy_web/adapters/inter_system_adapter.py), keyed by MetricDefinition.unit.
UNIT_NUMBER_FORMATS = {
    "K": "%.0f K",
    "%": "%.1f%%",
    "meV/atom": "%.2f meV/atom",
    "(meV/atom)²": "%.2f (meV/atom)²",
    "": "%.0f",
}


INTERACTION_DATA_PATH = (
    ROOT
    / "external"
    / "Rapid_Phase_Field_Prediction"
    / "input"
    / "spinodal"
    / "binary_interactions.json"
)
CACHE_PATH = ROOT / "alloy_web" / "data" / "inter_system_metrics.sqlite3"


st.set_page_config(
    page_title="Inter-System Comparison",
    page_icon=brand_favicon(),
    layout="wide",
)

st.markdown(
    """
    <style>
        .comparison-hero {
            padding: 1.55rem 1.7rem;
            margin-bottom: 1rem;
            border-radius: 1.15rem;
            color: white;
            background: linear-gradient(120deg, #3346a8 0%, #7848bd 52%, #c34f87 100%);
            box-shadow: 0 16px 36px rgba(70, 54, 145, 0.18);
        }
        .comparison-hero h1 { color: white; margin: 0 0 0.45rem; }
        .comparison-hero p { color: rgba(255,255,255,0.88); margin: 0; max-width: 830px; }
        .comparison-title { display: flex; align-items: center; gap: 0.85rem; }
        .comparison-icon {
            display: grid; place-items: center; flex: 0 0 auto;
            width: 3.2rem; height: 3.2rem; border-radius: 0.85rem;
            color: white; border: 1px solid rgba(255,255,255,0.28);
            background: rgba(255,255,255,0.12);
        }
        .metric-direction {
            display: inline-block; padding: 0.13rem 0.42rem; border-radius: 999px;
            background: rgba(91, 83, 183, 0.11); font-size: 0.72rem; font-weight: 700;
        }
    </style>
    <section class="comparison-hero">
        <div class="comparison-title">
            <div class="comparison-icon">__COMPARE_ICON__</div>
            <h1>Inter-System Comparison</h1>
        </div>
        <p>
            Turn an element pool into every fixed-order alloy system, rank the candidates,
            and reveal the Pareto set across the stability properties you care about.
        </p>
    </section>
    """.replace("__COMPARE_ICON__", icon_markup("compare", 30)),
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.markdown("#### How comparison works")
    st.caption(
        "Each candidate is an equimolar combination from the selected element pool. "
        "A composition counts as miscible only when at least 99% forms one BCC_A2, "
        "FCC_A1, or HCP_A3 solution; two composition sets of the same phase are multiphase. "
        "Spinodal temperature and the two pathway quantities are reported as context; "
        "none is treated as inherently better in either direction."
    )


PATHWAY_METRICS = [MEAN_PATH_BURDEN, PATH_BURDEN_VARIANCE]
metric_keys = [key for key in METRICS if key not in PATHWAY_METRICS]
default_metrics = [MISCIBILITY_TEMPERATURE, SPINODAL_TEMPERATURE, PMR]

with st.sidebar:
    st.header("Comparison inputs")
    element_pool = element_selector(
        "Element pool",
        default=["Cr", "Mo", "Nb", "Ta", "Ti", "W"],
        min_elements=2,
        max_elements=9,
        key="inter_system_element_pool",
    )

    max_order = min(5, len(element_pool))
    order_options = list(range(2, max_order + 1))
    system_order = st.selectbox(
        "System order",
        order_options or [2],
        index=max(0, len(order_options) - 2),
        format_func=lambda value: {
            2: "Binary", 3: "Ternary", 4: "Quaternary", 5: "Quinary"
        }.get(value, f"{value}-component"),
        help="Every combination of this size is compared.",
    )

    base_selected_metrics = st.multiselect(
        "Properties",
        metric_keys,
        default=default_metrics,
        format_func=lambda key: METRICS[key].label,
    )
    primary_metric = st.selectbox(
        "Primary ranking property",
        base_selected_metrics or [MISCIBILITY_TEMPERATURE],
        format_func=lambda key: METRICS[key].label,
        help="The table rank and leading chart use this property.",
    )

    include_pathway_metrics = st.checkbox(
        "Include path-burden landscape",
        value=False,
        disabled=system_order < 3,
        help=(
            "Calculate mean integrated burden and variance across every unique "
            "equimolar processing path. Available for ternary and higher systems."
        ),
    )
    if system_order < 3:
        include_pathway_metrics = False
    selected_metrics = list(base_selected_metrics)
    if include_pathway_metrics:
        selected_metrics.extend(PATHWAY_METRICS)

    reference_needed = bool(
        set(selected_metrics)
        & {
            PMR,
            EQUIMOLAR_SOLID_SOLUTION_FRACTION,
            ACTIVE_PHASE_COUNT,
            *PATHWAY_METRICS,
        }
    )
    reference_temperature = 1500.0
    if reference_needed:
        reference_temperature = float(
            st.number_input(
                "Reference temperature / K",
                min_value=100,
                max_value=5000,
                value=1500,
                step=50,
            )
        )

    pathway_points_per_segment = 5
    if include_pathway_metrics:
        with st.expander("Pathway resolution"):
            pathway_points_per_segment = int(
                st.number_input(
                    "Points per pathway segment",
                    min_value=2,
                    max_value=15,
                    value=5,
                    step=1,
                    help=(
                        "Applied equally to every composition segment. Higher values "
                        "increase the cost for every candidate system."
                    ),
                )
            )

    lattice = "BCC_A2"
    if set(selected_metrics) & {SPINODAL_TEMPERATURE, METASTABILITY_GAP}:
        lattice = st.selectbox("Spinodal lattice", ["BCC_A2", "FCC_A1", "HCP_A3"])

    with st.expander("Temperature search"):
        temperature_min = float(
            st.number_input(
                "Minimum temperature / K", min_value=100, max_value=4000,
                value=300, step=50,
            )
        )
        temperature_max = float(
            st.number_input(
                "Maximum temperature / K", min_value=200, max_value=5000,
                value=3000, step=50,
            )
        )
        temperature_step = float(
            st.number_input(
                "Coarse step / K", min_value=10, max_value=500,
                value=100, step=10,
                help="Miscibility crossings are refined to approximately 1 K.",
            )
        )

    valid_selection = (
        2 <= len(element_pool) <= 9
        and bool(selected_metrics)
        and system_order <= len(element_pool)
        and temperature_min < temperature_max
    )
    candidate_count = comb(len(element_pool), system_order) if valid_selection else 0
    st.caption(f"{candidate_count:,} candidate systems")
    if candidate_count > 50 and PMR in selected_metrics:
        st.info("The first PMR run is substantial; later identical runs use SQLite.")
    run_button = st.button(
        "Compare alloy systems", type="primary", disabled=not valid_selection,
        width="stretch",
    )


with st.expander("Comparison properties and interpretation"):
    columns = st.columns(2)
    for position, (key, definition) in enumerate(METRICS.items()):
        with columns[position % 2]:
            direction = {
                "higher": "Higher is favorable",
                "lower": "Lower is favorable",
                "context": "Context dependent · excluded from Pareto",
            }[definition.favorable]
            st.markdown(f"**{definition.label}** · <span class='metric-direction'>{direction}</span>", unsafe_allow_html=True)
            st.caption(definition.description)

with st.expander("Pareto-optimality rules"):
    st.markdown(
        """
        A candidate is **Pareto optimal** when no other complete candidate:

        - is at least as good on every property included in the Pareto comparison, **and**
        - is strictly better on at least one of those properties.

        PMR and equimolar solid-solution fraction are maximized. Miscibility temperature,
        active phase count, and metastability gap are minimized. Spinodal temperature is
        excluded because whether a higher or lower spinodal temperature is desirable depends
        on the intended alloy behavior. Mean path burden and path-burden variance are likewise
        treated as descriptive context, not optimization objectives. A candidate missing any
        included property is not placed on the Pareto set.
        """
    )


input_signature = (
    tuple(element_pool), int(system_order), tuple(selected_metrics), primary_metric,
    float(reference_temperature), float(temperature_min), float(temperature_max),
    float(temperature_step), lattice, int(pathway_points_per_segment),
)

if run_button:
    progress = st.progress(0.0, text="Preparing candidate systems…")

    def update_progress(completed: int, total: int, system: str):
        progress.progress(completed / total, text=f"{system} · {completed:,} of {total:,}")

    try:
        result = run_inter_system_comparison(
            element_pool=element_pool,
            order=int(system_order),
            selected_metrics=selected_metrics,
            primary_metric=primary_metric,
            reference_temperature=reference_temperature,
            temperature_min=temperature_min,
            temperature_max=temperature_max,
            temperature_step=temperature_step,
            lattice=lattice,
            tdb_dir=TDB_DIR,
            interaction_data_path=INTERACTION_DATA_PATH,
            cache_path=CACHE_PATH,
            miscibility_threshold=0.99,
            max_sample_points=400,
            pathway_points_per_segment=pathway_points_per_segment,
            progress_callback=update_progress,
        )
        progress.empty()
        st.session_state["inter_system_result"] = result
        st.session_state["inter_system_signature"] = input_signature
    except Exception as exc:
        progress.empty()
        st.error("Inter-system comparison failed.")
        st.code(str(exc))
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())


result = None
if st.session_state.get("inter_system_signature") == input_signature:
    result = st.session_state.get("inter_system_result")


def ranking_figure(result):
    metric = result.primary_metric
    definition = METRICS[metric]
    if definition.favorable == "context":
        return None
    plot_data = result.data.dropna(subset=[metric]).head(30).sort_values(metric)
    if plot_data.empty:
        return None
    colors = ["#d64c87" if value else "#5269c7" for value in plot_data["Pareto optimal"]]
    fig, ax = plt.subplots(figsize=(8.2, max(4.0, 0.31 * len(plot_data) + 1.1)))
    ax.barh(plot_data["System"], plot_data[metric], color=colors, alpha=0.92)
    ax.set_xlabel(f"{definition.label}{f' ({definition.unit})' if definition.unit else ''}")
    ax.set_title(f"Ranked by {definition.label}", loc="left", fontweight="bold")
    ax.grid(axis="x", alpha=0.18)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    return fig


def desirability_figure(result):
    comparison_metrics = [
        metric for metric in result.selected_metrics
        if METRICS[metric].favorable in {"higher", "lower"}
    ]
    if not comparison_metrics:
        return None
    plot_data = result.data.dropna(subset=comparison_metrics).head(20).copy()
    if plot_data.empty:
        return None
    desirability = []
    for metric in comparison_metrics:
        values = plot_data[metric].to_numpy(dtype=float)
        spread = values.max() - values.min()
        normalized = np.full(len(values), 0.5) if spread == 0 else (values - values.min()) / spread
        if METRICS[metric].favorable == "lower":
            normalized = 1.0 - normalized
        desirability.append(100.0 * normalized)
    matrix = np.column_stack(desirability)
    fig, ax = plt.subplots(figsize=(max(6.8, 1.7 * len(comparison_metrics)), max(4.2, 0.36 * len(plot_data) + 1.4)))
    image = ax.imshow(matrix, aspect="auto", cmap="viridis", vmin=0, vmax=100)
    ax.set_xticks(range(len(comparison_metrics)), [METRICS[key].label for key in comparison_metrics], rotation=24, ha="right")
    ax.set_yticks(range(len(plot_data)), plot_data["System"])
    ax.set_title("Normalized property comparison", loc="left", fontweight="bold")
    for row in range(len(plot_data)):
        for column, metric in enumerate(comparison_metrics):
            ax.text(column, row, plot_data.iloc[row][f"{metric}__display"], ha="center", va="center", fontsize=7.5, color="white" if matrix[row, column] < 42 else "black")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.78)
    colorbar.set_label("Normalized score (0–100)")
    fig.tight_layout()
    return fig


def pathway_context_figure(result):
    if not set(PATHWAY_METRICS).issubset(result.data.columns):
        return None
    plot_data = result.data.dropna(subset=PATHWAY_METRICS).copy()
    if plot_data.empty:
        return None
    return plot_system_path_burden_landscape(
        plot_data,
        mean_column=MEAN_PATH_BURDEN,
        variance_column=PATH_BURDEN_VARIANCE,
    )


if result is not None:
    st.markdown("## Comparison results")
    metric_columns = st.columns(6)
    metric_columns[0].metric("Candidates", f"{result.candidate_count:,}")
    metric_columns[1].metric("Complete", f"{result.complete_count:,}")
    metric_columns[2].metric("Pareto set", f"{result.pareto_count:,}")
    metric_columns[3].metric("Cache hits", f"{result.cache_hits:,}")
    metric_columns[4].metric("Calculations", f"{result.equilibrium_calculations:,}")
    metric_columns[5].metric("Runtime", f"{result.elapsed_seconds:.2f} s")
    st.caption(
        "SQLite stores computed metrics by system, settings, and source-file version. "
        "TDB files are read-only inputs and are never altered."
    )
    if not result.pareto_metrics:
        st.info(
            "No Pareto set is shown because spinodal temperature is the only selected property; "
            "it has no universal favorable direction."
        )

    table = result.data[["Rank", "System", "Pareto optimal"]].copy()
    column_config = {
        "Rank": st.column_config.NumberColumn(width="small", format="%d"),
        "Pareto optimal": st.column_config.CheckboxColumn(width="small"),
    }
    for metric in result.selected_metrics:
        # Use the numeric value, not the "1500 K" / "≤ 300 K" display string:
        # st.dataframe sorts by the underlying cell value, so a text column
        # sorts lexicographically ("1500 K" before "300 K"). NumberColumn's
        # `format` still renders the unit, but sorting stays numeric.
        label = METRICS[metric].label
        table[label] = result.data[metric]
        column_config[label] = st.column_config.NumberColumn(
            format=UNIT_NUMBER_FORMATS.get(METRICS[metric].unit, "%.2f"),
            help=METRICS[metric].description,
        )
    table["Solid solution phase"] = result.data["Solid solution phase"]
    table["Data status"] = result.data["Data status"]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )
    st.caption(
        "Columns sort numerically on click. A blank cell means the property "
        "was unavailable for that system (see Data status); a temperature "
        "shown at the scan floor or ceiling may be a bound rather than an "
        "exact crossing."
    )

    pathway_figure = pathway_context_figure(result)
    if pathway_figure is not None:
        st.markdown("### Path-burden landscape")
        st.caption(
            "Each point is one alloy system at the selected reference temperature. "
            "The axes provide comparative context only: neither high nor low mean "
            "burden or variance is assigned a universally favorable meaning."
        )
        st.pyplot(pathway_figure, width="stretch")
        plt.close(pathway_figure)
        if result.candidate_count > 40:
            st.caption(
                "System labels are omitted above 40 candidates to keep the plot readable; "
                "the table and CSV identify every point."
            )

    left, right = st.columns([0.92, 1.08])
    with left:
        figure = ranking_figure(result)
        if figure is not None:
            st.pyplot(figure, width="stretch")
            plt.close(figure)
            if result.complete_count > 30:
                st.caption("Chart shows the first 30 ranked candidates; the table and download include all systems.")
    with right:
        figure = desirability_figure(result)
        if figure is not None:
            st.pyplot(figure, width="stretch")
            plt.close(figure)
        else:
            st.info("No candidates have complete values across all selected properties.")

    st.download_button(
        "Download comparison CSV",
        data=result.to_csv_bytes(),
        file_name=f"inter_system_{len(element_pool)}-element_pool_{system_order}-component.csv",
        mime="text/csv",
    )
else:
    st.info("Choose an element pool, system order, and properties, then run the comparison.")
