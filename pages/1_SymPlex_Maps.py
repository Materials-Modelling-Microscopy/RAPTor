from pathlib import Path
import sys
import traceback
import matplotlib.pyplot as plt
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports
from alloy_web.ui import element_selector, show_input_summary, figure_to_png_bytes
from alloy_web.adapters.symplex_adapter import run_symplex_prediction


ensure_project_imports()

st.set_page_config(
    page_title="SymPlex Maps",
    layout="wide",
)

st.title("SymPlex Maps")

st.markdown(
    """
    Generate quaternary or quinary SymPlex property maps.
    
    (The function is currently slow, please have patience!)

    """
)

AVAILABLE_PROPERTIES = [
    "SPSS Phase Fraction",
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


if run_button:
    try:
        with st.spinner("Running SymPlex prediction..."):
            result = run_symplex_prediction(
                alloy_system=alloy_system,
                temperature=float(temperature),
                constraint_element=constraint_element,
                property_name=property_name,
            )

        with right:
            st.subheader("SymPlex plot")
            st.pyplot(result.figure, use_container_width=False)

        st.subheader("Raw path-wise data")

        st.write(f"Number of paths: `{len(result.data)}`")

        if result.data:
            preview_key = list(result.data.keys())[0]
            st.write(f"Preview path: `{preview_key}`")
            st.write(result.data[preview_key][:10])

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                "Download raw data",
                data=result.to_pickle_bytes(),
                file_name=(
                    f"{'-'.join(result.alloy_system)}_"
                    f"{result.temperature:.0f}K_"
                    f"{result.property_name.replace(' ', '_')}.pkl"
                ),
                mime="application/octet-stream",
            )

        with col2:
            st.download_button(
                "Download plot PNG",
                data=figure_to_png_bytes(result.figure),
                file_name=(
                    f"{'-'.join(result.alloy_system)}_"
                    f"{result.temperature:.0f}K_"
                    f"{result.property_name.replace(' ', '_')}.png"
                ),
                mime="image/png",
            )

        plt.close(result.figure)

    except Exception as exc:
        pass
        # st.error("SymPlex prediction failed.")
        # st.code(str(exc))
        #
        # with st.expander("Full traceback"):
        #     st.code(traceback.format_exc())
