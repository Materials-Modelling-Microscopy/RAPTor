from pathlib import Path
import sys
import traceback

import matplotlib.pyplot as plt
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports, TDB_DIR
from alloy_web.icons import brand_favicon, page_title
from alloy_web.ui import (
    element_selector,
    figure_to_png_bytes,
    mole_fraction_inputs,
    show_input_summary,
    show_result_data,
)


ensure_project_imports()

from alloy_web.adapters.pathway_adapter import run_pathway_analysis
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.pathway_analysis import (
    plot_path_energy_profiles,
    plot_path_phase_fractions,
)


st.set_page_config(
    page_title="Processing Pathways",
    page_icon=brand_favicon(),
    layout="wide",
)

page_title(
    "Processing Pathways",
    "diagram",
    subtitle=(
        "Compare how sequential alloying routes accumulate solid-solution "
        "thermodynamic burden."
    ),
)

with st.container(border=True):
    st.markdown("#### What the two pathway quantities mean")
    st.caption(
        "Each route is scored by the integral of homogeneous BCC_A2 energy above "
        "equilibrium along a normalized binary-to-final composition path. Mean path "
        "burden describes the overall thermodynamic cost of retaining BCC_A2; variance "
        "between path integrals measures how strongly that cost depends on processing order."
    )


with st.sidebar:
    st.header("Pathway inputs")

    alloy_system = element_selector(
        "Alloy system",
        default=["Nb", "Ti", "V", "Zr"],
        min_elements=3,
        max_elements=5,
    )

    mol_ratio = mole_fraction_inputs(alloy_system)

    temperature = st.number_input(
        "Temperature / K",
        min_value=100,
        max_value=5000,
        value=1500,
        step=50,
    )

    with st.expander("Path resolution"):
        points_per_segment = st.number_input(
            "Points per composition segment",
            min_value=2,
            max_value=31,
            value=9,
            step=1,
            help=(
                "Every binary-to-ternary or higher-order segment receives "
                "the same number of calculation points."
            ),
        )

    valid_inputs = (
        3 <= len(alloy_system) <= 5
        and len(mol_ratio) == len(alloy_system)
        and all(fraction > 0.0 for fraction in mol_ratio)
        and abs(sum(mol_ratio) - 1.0) < 1e-6
    )
    run_button = st.button(
        "Analyze processing pathways",
        type="primary",
        disabled=not valid_inputs,
        width="stretch",
    )


input_signature = (
    tuple(alloy_system),
    tuple(float(fraction) for fraction in mol_ratio),
    float(temperature),
    int(points_per_segment),
)

left, right = st.columns([1, 2.1])
with left:
    show_input_summary(
        {
            "alloy_system": alloy_system,
            "mole_fractions": mol_ratio,
            "temperature_K": float(temperature),
            "points_per_segment": int(points_per_segment),
        },
        title="Pathway inputs",
    )


if run_button:
    try:
        with st.spinner("Evaluating all unique processing paths..."):
            result = run_pathway_analysis(
                alloy_system=alloy_system,
                mol_ratio=mol_ratio,
                temperature=float(temperature),
                tdb_dir=TDB_DIR,
                points_per_segment=int(points_per_segment),
            )
        st.session_state["pathway_result"] = result
        st.session_state["pathway_signature"] = input_signature
    except Exception as exc:
        st.error("Processing-pathway analysis failed.")
        st.code(str(exc))
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())


result = None
if st.session_state.get("pathway_signature") == input_signature:
    result = st.session_state.get("pathway_result")


if result is not None:
    with right:
        st.markdown(f"## {' – '.join(result.alloy_system)} at {result.temperature:.0f} K")
        metric_left, metric_right = st.columns(2)
        with metric_left:
            st.metric(
                "Mean integrated path burden",
                f"{result.mean_integrated_burden:.2f} meV/atom",
            )
        with metric_right:
            st.metric(
                "Path-dependence variance",
                f"{result.path_dependence_variance:.2f} (meV/atom)²",
            )
        st.caption(
            f"{len(result.paths)} unique thermodynamic paths · "
            f"{result.points_per_segment} points per segment"
        )

    st.markdown("## Paths grouped by starting binary")
    st.caption(
        "The first two elemental orderings are thermodynamically equivalent, so each "
        "tab represents one unique binary precursor rather than duplicating A→B and B→A."
    )

    tabs = st.tabs(
        [binary.replace("-", " – ") for binary in result.starting_binaries]
    )

    for tab, starting_binary in zip(tabs, result.starting_binaries):
        with tab:
            path_ids = result.path_ids_for_starting_binary(starting_binary)
            binary_paths = result.paths[
                result.paths["path_id"].isin(path_ids)
            ].sort_values("integrated_burden_meV_per_atom")

            energy_figure = plot_path_energy_profiles(
                result.path_points,
                path_ids=path_ids,
            )
            st.pyplot(energy_figure, width="stretch")

            selected_path_id = st.selectbox(
                "Inspect equilibrium phase fractions",
                binary_paths["path_id"].astype(int).tolist(),
                format_func=lambda path_id: binary_paths.loc[
                    binary_paths["path_id"] == path_id,
                    "path",
                ].iloc[0],
                key=f"pathway_phase_path_{starting_binary}",
            )
            selected_path = binary_paths[
                binary_paths["path_id"] == selected_path_id
            ].iloc[0]
            st.caption(
                "Integrated burden: "
                f"{selected_path['integrated_burden_meV_per_atom']:.2f} meV/atom"
            )

            phase_figure = plot_path_phase_fractions(
                result.phase_fractions,
                path_id=selected_path_id,
            )
            st.pyplot(phase_figure, width="stretch")

            download_left, download_right = st.columns(2)
            with download_left:
                st.download_button(
                    "Download burden plot",
                    data=figure_to_png_bytes(energy_figure),
                    file_name=(
                        f"{'-'.join(result.alloy_system)}_"
                        f"{starting_binary}_path_burden.png"
                    ),
                    mime="image/png",
                    key=f"pathway_energy_download_{starting_binary}",
                )
            with download_right:
                st.download_button(
                    "Download phase-fraction plot",
                    data=figure_to_png_bytes(phase_figure),
                    file_name=(
                        f"{'-'.join(result.alloy_system)}_"
                        f"path_{selected_path_id}_phase_fractions.png"
                    ),
                    mime="image/png",
                    key=f"pathway_phase_download_{starting_binary}",
                )

            plt.close(energy_figure)
            plt.close(phase_figure)

    st.markdown("## Pathway data")
    path_download = result.paths.copy()
    path_download["representative_order"] = path_download[
        "representative_order"
    ].map(lambda order: " → ".join(order))
    path_download["equivalent_orders"] = path_download[
        "equivalent_orders"
    ].map(
        lambda orders: " | ".join(" → ".join(order) for order in orders)
    )

    show_result_data(
        data=path_download,
        title="Integrated burden by path",
        file_name=f"{'-'.join(result.alloy_system)}_path_burdens.csv",
        key_prefix="pathway_burdens",
    )
    show_result_data(
        data=result.path_points,
        title="Energy along paths",
        file_name=f"{'-'.join(result.alloy_system)}_path_points.csv",
        key_prefix="pathway_points",
    )
    show_result_data(
        data=result.phase_fractions,
        title="Equilibrium phase fractions along paths",
        file_name=f"{'-'.join(result.alloy_system)}_path_phase_fractions.csv",
        key_prefix="pathway_phase_fractions",
    )
