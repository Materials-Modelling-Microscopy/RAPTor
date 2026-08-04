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
from alloy_web.ui import element_selector, show_input_summary, figure_to_png_bytes
from alloy_web.adapters.phasefield_adapter import run_phase_diagram_prediction


ensure_project_imports()

st.set_page_config(
    page_title="Phase Diagrams",
    page_icon=brand_favicon(),
    layout="wide",
)

page_title("Binary and Ternary Phase Diagrams", "diagram")

st.markdown(
    """
    Generate binary temperature-composition diagrams or ternary isothermal sections.

    """
)


with st.sidebar:
    st.header("Phase diagram inputs")

    alloy_system = element_selector(
        "Alloy system",
        default=["Cr", "Mo"],
        min_elements=2,
        max_elements=3,
    )

    include_intermetallics = True

    composition_step = st.number_input(
        "Composition step",
        min_value=0.001,
        max_value=0.1,
        value=0.02,
        step=0.005,
        format="%.3f",
    )

    temperature_min = 300
    temperature_max = 3000
    temperature_step = 10
    ternary_temperature = None
    ternary_order = 0

    if len(alloy_system) == 2:
        st.markdown("### Binary settings")

        temperature_min = st.number_input(
            "Minimum temperature / K",
            min_value=100,
            max_value=4000,
            value=300,
            step=50,
        )

        temperature_max = st.number_input(
            "Maximum temperature / K",
            min_value=100,
            max_value=5000,
            value=3000,
            step=50,
        )

        temperature_step = st.number_input(
            "Temperature step / K",
            min_value=1,
            max_value=500,
            value=10,
            step=10,
        )

    elif len(alloy_system) == 3:
        st.markdown("### Ternary settings")

        ternary_temperature = st.number_input(
            "Temperature / K",
            min_value=100,
            max_value=5000,
            value=1500,
            step=50,
        )

        ternary_order = st.selectbox(
            "Element ordering permutation",
            list(range(6)),
            index=0,
        )

    run_button = st.button("Generate phase diagram", type="primary")


left, right = st.columns([1, 1.5])


if run_button:
    try:
        with left:
            show_input_summary(
                {
                    "alloy_system": alloy_system,
                    "diagram_type": "binary" if len(alloy_system) == 2 else "ternary",
                    "include_intermetallics": include_intermetallics,
                    "composition_step": composition_step,
                    "temperature_min": temperature_min,
                    "temperature_max": temperature_max,
                    "temperature_step": temperature_step,
                    "ternary_temperature": ternary_temperature,
                    "ternary_order": ternary_order,
                    "tdb_dir": str(TDB_DIR),
                }
            )
        with st.spinner("Generating phase diagram..."):
            result = run_phase_diagram_prediction(
                alloy_system=alloy_system,
                tdb_dir=TDB_DIR,
                temperature=(
                    float(ternary_temperature)
                    if ternary_temperature is not None
                    else None
                ),
                include_intermetallics=include_intermetallics,
                ternary_order=int(ternary_order),
                temperature_min=float(temperature_min),
                temperature_max=float(temperature_max),
                temperature_step=float(temperature_step),
                composition_step=float(composition_step),
            )

        with right:
            st.subheader(f"{result.diagram_type.title()} phase diagram")
            st.pyplot(result.figure, use_container_width=True)

        st.download_button(
            "Download plot PNG",
            data=figure_to_png_bytes(result.figure),
            file_name=f"{result.composition}_{result.diagram_type}.png",
            mime="image/png",
        )

        plt.close(result.figure)

    except Exception as exc:
        st.error("Phase diagram generation failed.")
        st.code(str(exc))

        with st.expander("Full traceback"):
            st.code(traceback.format_exc())
