from pathlib import Path
import sys
from time import perf_counter
import traceback
import matplotlib.pyplot as plt
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports
from alloy_web.icons import brand_favicon, page_title
from alloy_web.ui import element_selector, show_input_summary, figure_to_png_bytes


ensure_project_imports()

from alloy_web.adapters.symplex_adapter import run_symplex_prediction

st.set_page_config(
    page_title="SymPlex Maps",
    page_icon=brand_favicon(),
    layout="wide",
)

page_title(
    "SymPlex Maps",
    "symplex",
    "Map composition-dependent thermodynamic properties across quaternary and quinary systems.",
)

AVAILABLE_PROPERTIES = [
    "SPSS Phase Fraction",
    "BCC Energy Above Hull",
    "Number of Phases",
    "Minimum Spinodal Eigenvalue",
]


with st.sidebar:
    st.header("SymPlex inputs")

    alloy_system = element_selector(
        "Alloy system",
        default=["Cr", "Mo", "Nb", "Ta"],
        min_elements=4,
        max_elements=5,
    )

    temperature = st.number_input(
        "Temperature / K",
        min_value=300,
        max_value=3000,
        value=1500,
        step=300,
    )

    property_name = st.selectbox(
        "Property",
        AVAILABLE_PROPERTIES,
    )

    constraint_element = None
    if alloy_system:
        constraint_element = st.selectbox(
            "Constraint element",
            alloy_system,
        )

    run_button = st.button("Run SymPlex prediction", type="primary")


left, right = st.columns([1, 1.4])

with left:
    show_input_summary(
        {
            "alloy_system": alloy_system,
            "temperature": temperature,
            "property_name": property_name,
            "constraint_element": constraint_element,
        }
    )
    if property_name == "BCC Energy Above Hull":
        st.caption(
            "Homogeneous BCC_A2 Gibbs energy minus the equilibrium Gibbs hull at each "
            "composition, reported in meV/atom. Zero is stable; up to 50 meV/atom is "
            "shown as metastable."
        )
    calculation_summary = st.empty()


if run_button:
    try:
        with st.spinner("Running SymPlex prediction..."):
            prediction_started_at = perf_counter()
            result = run_symplex_prediction(
                alloy_system=alloy_system,
                temperature=float(temperature),
                constraint_element=constraint_element,
                property_name=property_name,
            )
            prediction_seconds = perf_counter() - prediction_started_at
            calculation_count = sum(len(values) for values in result.data.values())
            
            png_bytes = figure_to_png_bytes(result.figure)
            
            
        
        
        calculation_summary.caption(
            f"{calculation_count:,} calculations in {prediction_seconds:.2f} seconds."
        )

        with right:
            st.subheader("SymPlex map")
            st.image(
                png_bytes,
                caption=f"{'-'.join(result.alloy_system)} | {result.property_name} | {result.temperature:.0f} K",
                use_container_width=True,
            )
        
        st.download_button(
            "Download plot PNG",
            data=png_bytes,
            file_name=f"{'-'.join(result.alloy_system)}_{result.property_name}_{result.temperature:.0f}K.png",
            mime="image/png",
        )
        
        plt.close(result.figure)

    except Exception as exc:
        # pass
        st.error("SymPlex prediction failed.")
        st.code(str(exc))

        with st.expander("Full traceback"):
            st.code(traceback.format_exc())
