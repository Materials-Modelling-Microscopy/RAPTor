from pathlib import Path
import sys
import traceback
import matplotlib.pyplot as plt
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports
from alloy_web.icons import brand_favicon, page_title
from alloy_web.ui import element_selector, mole_fraction_inputs, show_input_summary
from alloy_web.adapters.spinodal_adapter import run_spinodal_analysis

ensure_project_imports()

SPINODAL_DATA_PATH = (
    ROOT
    / "external"
    / "Rapid_Phase_Field_Prediction"
    / "input"
    / "spinodal"
    / "binary_interactions.json"
)

st.set_page_config(
    page_title="Spinodal Analysis",
    page_icon=brand_favicon(),
    layout="wide",
)

page_title("Spinodal Analysis", "spinodal")

st.markdown(
    """
    Analyze spinodal instability for a fixed alloy composition.

    This page shows:
    - Hessian eigenvalues as a function of temperature
    - estimated spinodal temperature
    - soft mode eigenvector at a selected temperature
    """
)

with st.sidebar:
    st.header("Spinodal inputs")

    alloy_system = element_selector(
        "Alloy system",
        default=["Cr", "Mo", "Nb", "Ta"],
        min_elements=2,
        max_elements=6,
    )

    lattice = st.selectbox(
        "Lattice",
        ["BCC_A2", "FCC_A1", "HCP_A3"],
        index=0,
    )

    temperature_min = st.number_input(
        "Minimum temperature / K",
        min_value=100,
        max_value=5000,
        value=300,
        step=50,
    )

    temperature_max = st.number_input(
        "Maximum temperature / K",
        min_value=100,
        max_value=5000,
        value=2500,
        step=50,
    )

    temperature_step = st.number_input(
        "Temperature step / K",
        min_value=1,
        max_value=500,
        value=50,
        step=10,
    )

    mode_temperature = st.number_input(
        "Temperature for eigenvector plot / K",
        min_value=100,
        max_value=5000,
        value=1500,
        step=50,
    )

    run_button = st.button("Run spinodal analysis", type="primary")


left, right = st.columns([1, 1.5])

with left:
    mol_ratio = mole_fraction_inputs(alloy_system)

    show_input_summary(
        {
            "alloy_system": alloy_system,
            "mol_ratio": mol_ratio,
            "lattice": lattice,
            "temperature_min": temperature_min,
            "temperature_max": temperature_max,
            "temperature_step": temperature_step,
            "mode_temperature": mode_temperature,
        },
        title="Spinodal inputs",
    )

if run_button:
    try:
        with st.spinner("Running spinodal analysis..."):
            result = run_spinodal_analysis(
                alloy_system=alloy_system,
                mol_ratio=mol_ratio,
                lattice=lattice,
                temperature_min=float(temperature_min),
                temperature_max=float(temperature_max),
                temperature_step=float(temperature_step),
                mode_temperature=float(mode_temperature),
                interaction_data_path=SPINODAL_DATA_PATH,
            )

        with right:
            st.subheader("Eigenvalues vs temperature")
            st.pyplot(result.eigenvalue_figure, use_container_width=True)

        if result.spinodal_temperature is not None:
            st.success(f"Estimated spinodal temperature: {result.spinodal_temperature:.1f} K")
        else:
            st.info("No zero crossing of the minimum eigenvalue was detected in the selected temperature range.")

        st.subheader("Soft mode eigenvector")
        st.pyplot(result.mode_figure, use_container_width=True)

        st.subheader("Mode interpretation")
        st.write(
            {
                "positive_group": result.interpretation["positive_group"],
                "negative_group": result.interpretation["negative_group"],
                "near_zero": result.interpretation["near_zero"],
            }
        )

        st.subheader("Spinodal spectrum data")
        st.dataframe(result.spectrum_data, use_container_width=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                "Download CSV",
                data=result.to_csv_bytes(),
                file_name=f"{'-'.join(result.alloy_system)}_spinodal_spectrum.csv",
                mime="text/csv",
            )

        with col2:
            st.download_button(
                "Download eigenvalue plot",
                data=result.fig_to_png_bytes(result.eigenvalue_figure),
                file_name=f"{'-'.join(result.alloy_system)}_spinodal_eigenvalues.png",
                mime="image/png",
            )

        with col3:
            st.download_button(
                "Download eigenvector plot",
                data=result.fig_to_png_bytes(result.mode_figure),
                file_name=f"{'-'.join(result.alloy_system)}_spinodal_mode.png",
                mime="image/png",
            )

        plt.close(result.eigenvalue_figure)
        plt.close(result.mode_figure)

    except Exception as exc:
        st.error("Spinodal analysis failed.")
        st.code(str(exc))

        with st.expander("Full traceback"):
            st.code(traceback.format_exc())
