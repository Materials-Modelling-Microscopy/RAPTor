from pathlib import Path
import sys
import traceback
import matplotlib.pyplot as plt
import streamlit as st
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports, TDB_DIR
from alloy_web.ui import (
    element_selector,
    mole_fraction_inputs,
    show_input_summary,
    figure_to_png_bytes,
)
from alloy_web.adapters.phasefield_adapter import (
    run_phase_fraction_temperature_prediction,
    run_composition_splitting_prediction,
)


ensure_project_imports()

st.set_page_config(
    page_title="Phase Fractions",
    layout="wide",
)


def _default_composition_text(n_elements: int) -> str:
    """
    Generate a simple default set of nearby compositions.
    Works for binary through quinary systems.
    """
    base = np.ones(n_elements) / n_elements

    rows = [base]

    if n_elements >= 2:
        perturb = 0.05

        row_1 = base.copy()
        row_1[0] += perturb
        row_1[1:] -= perturb / (n_elements - 1)
        rows.append(row_1)

        row_2 = base.copy()
        row_2[0] -= perturb
        row_2[1:] += perturb / (n_elements - 1)
        rows.append(row_2)

    cleaned_rows = []
    for row in rows:
        row = np.clip(row, 0.0, 1.0)
        row = row / row.sum()
        cleaned_rows.append(",".join(f"{x:.4f}" for x in row))

    return "\n".join(cleaned_rows)


def _parse_composition_rows(raw_text: str, n_elements: int) -> list[list[float]]:
    """
    Parse composition rows from text area.

    Expected format:
        0.25,0.25,0.25,0.25
        0.30,0.20,0.25,0.25
    """
    rows = []

    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()

        if not line:
            continue

        parts = [x.strip() for x in line.replace(" ", ",").split(",") if x.strip()]
        values = [float(x) for x in parts]

        if len(values) != n_elements:
            raise ValueError(
                f"Composition row {line_no} has {len(values)} values, "
                f"but the selected alloy system has {n_elements} elements."
            )

        total = sum(values)
        if not np.isclose(total, 1.0, atol=1e-4):
            raise ValueError(
                f"Composition row {line_no} must sum to 1. "
                f"Current sum = {total:.6f}."
            )

        rows.append(values)

    if len(rows) == 0:
        raise ValueError("Enter at least one composition row.")

    return rows


def _parse_temperatures(raw_text: str) -> list[float]:
    """
    Parse up to 3 temperatures from comma-separated text.
    """
    parts = [x.strip() for x in raw_text.replace(" ", ",").split(",") if x.strip()]
    temperatures = [float(x) for x in parts]

    if len(temperatures) == 0:
        raise ValueError("Enter at least one temperature.")

    if len(temperatures) > 3:
        raise ValueError("Enter at most 3 temperatures.")

    return temperatures


st.title("Phase Fractions and Composition Splitting")

st.markdown(
    """
    Compute equilibrium phase fractions either as a function of temperature
    for a fixed alloy composition, or as composition-dependent phase splitting
    at selected temperatures.
    """
)


with st.sidebar:
    st.header("Phase-field inputs")

    analysis_mode = st.radio(
        "Analysis mode",
        [
            "Phase fractions vs temperature",
            "Composition splitting at selected temperatures",
        ],
    )

    alloy_system = element_selector(
        "Alloy system",
        default=["Cr", "Mo", "Nb", "Ta"],
        min_elements=2,
        max_elements=5,
    )

    if analysis_mode == "Phase fractions vs temperature":
        temperature_min = st.number_input(
            "Minimum temperature / K",
            min_value=300,
            max_value=4000,
            value=300,
            step=50,
        )

        temperature_max = st.number_input(
            "Maximum temperature / K",
            min_value=300,
            max_value=5000,
            value=3000,
            step=50,
        )

        temperature_step = st.number_input(
            "Temperature step / K",
            min_value=1,
            max_value=500,
            value=100,
            step=100,
        )

        mol_ratio = mole_fraction_inputs(alloy_system)

        run_button = st.button(
            "Run phase fraction prediction",
            type="primary",
        )

    else:
        temperatures_text = st.text_input(
            "Temperatures / K, up to 3",
            value="500,1000,1500",
        )

        default_text = _default_composition_text(len(alloy_system))

        mols_text = st.text_area(
            "Compositions, one row per alloy",
            value=default_text,
            height=160,
            help=(
                "Each row should contain mole fractions in the same order as the selected "
                "alloy system. Each row must sum to 1."
            ),
        )

        run_button = st.button(
            "Run composition splitting prediction",
            type="primary",
        )


left, right = st.columns([1, 1.4])


if run_button:
    if analysis_mode == "Phase fractions vs temperature":
        try:
            with left:
                show_input_summary(
                    {
                        "alloy_system": alloy_system,
                        "mol_ratio": mol_ratio,
                        "temperature_min": temperature_min,
                        "temperature_max": temperature_max,
                        "temperature_step": temperature_step,
                        "tdb_dir": str(TDB_DIR),
                    }
                )

            with st.spinner("Running phase fraction prediction..."):
                result = run_phase_fraction_temperature_prediction(
                    alloy_system=alloy_system,
                    mol_ratio=mol_ratio,
                    temperature_min=float(temperature_min),
                    temperature_max=float(temperature_max),
                    temperature_step=float(temperature_step),
                    tdb_dir=TDB_DIR,
                )

            with right:
                st.subheader("Phase fraction plot")
                st.pyplot(result.figure, use_container_width=True)

            st.subheader("Phase fraction data")
            st.dataframe(result.data, use_container_width=True)

            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    "Download CSV",
                    data=result.to_csv_bytes(),
                    file_name=f"{result.composition}_phase_fractions.csv",
                    mime="text/csv",
                )

            with col2:
                st.download_button(
                    "Download plot PNG",
                    data=figure_to_png_bytes(result.figure),
                    file_name=f"{result.composition}_phase_fractions.png",
                    mime="image/png",
                )

            plt.close(result.figure)

        except Exception as exc:
            st.error("Phase fraction prediction failed.")
            st.code(str(exc))

            with st.expander("Full traceback"):
                st.code(traceback.format_exc())

    else:
        try:
            temperatures = _parse_temperatures(temperatures_text)
            mols = _parse_composition_rows(
                raw_text=mols_text,
                n_elements=len(alloy_system),
            )

            with left:
                show_input_summary(
                    {
                        "alloy_system": alloy_system,
                        "temperatures": temperatures,
                        "number_of_compositions": len(mols),
                        "tdb_dir": str(TDB_DIR),
                    },
                    title="Composition splitting inputs",
                )

                st.markdown("#### Composition rows")
                st.dataframe(
                    {
                        element: [row[i] for row in mols]
                        for i, element in enumerate(alloy_system)
                    },
                    use_container_width=True,
                )

            with st.spinner("Running composition splitting prediction..."):
                result = run_composition_splitting_prediction(
                    alloy_system=alloy_system,
                    mols=mols,
                    temperatures=temperatures,
                    tdb_dir=TDB_DIR,
                )

            tabs = st.tabs(
                [f"{single.temperature:.0f} K" for single in result.results]
            )

            for tab, single in zip(tabs, result.results):
                with tab:
                    st.subheader(f"Composition splitting at {single.temperature:.0f} K")

                    st.pyplot(single.figure, use_container_width=True)

                    st.subheader("Composition splitting data")
                    st.dataframe(single.data, use_container_width=True)

                    col1, col2 = st.columns(2)

                    with col1:
                        st.download_button(
                            "Download CSV",
                            data=single.to_csv_bytes(),
                            file_name=(
                                f"{'-'.join(result.alloy_system)}_"
                                f"{single.temperature:.0f}K_composition_splitting.csv"
                            ),
                            mime="text/csv",
                        )

                    with col2:
                        st.download_button(
                            "Download plot PNG",
                            data=single.to_png_bytes(),
                            file_name=(
                                f"{'-'.join(result.alloy_system)}_"
                                f"{single.temperature:.0f}K_composition_splitting.png"
                            ),
                            mime="image/png",
                        )

                    plt.close(single.figure)

        except Exception as exc:
            st.error("Composition splitting prediction failed.")
            st.code(str(exc))

            with st.expander("Full traceback"):
                st.code(traceback.format_exc())