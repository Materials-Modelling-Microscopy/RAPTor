from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports

ensure_project_imports()

st.set_page_config(
    page_title="RAPGen",
    page_icon="🧪",
    layout="wide",
)

LAB_URL = "https://mcube.wustl.edu"
PROFILE_URL = "https://github.com/Pravanop/"
REPO_URL = "https://github.com/Pravanop/Phase_Field_Prediction_Visualization"
CONTACT_EMAIL = "mailto:rmishra@wustl.edu"

st.title("RAPGen")
st.header("Rapid Alloy Phase-field Generator")

st.markdown(
    """
    **RAPGen** is a web-based interface for rapid thermodynamic prediction and
    visualization of phase stability in multicomponent alloys. The interface
    provides interactive tools for generating phase diagrams, phase-fraction
    profiles, SymPlex composition maps, and spinodal decomposition metrics from
    alloy thermodynamic models.
    """
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Phase diagrams", "Binary / Ternary", format = 'compact')

with col2:
    st.metric("Composition space", "HEAs")

with col3:
    st.metric("Temperature profiles", "Phase Splitting")

with col4:
    st.metric("Spinodal Decomposition", "Unstable modes")

st.divider()

left, right = st.columns([1.2, 1])

with left:
    with st.container(border=True):
        st.subheader("What you can do here")

        st.markdown(
            """
            - Generate **binary temperature–composition phase diagrams**.
            - Generate **isothermal ternary phase diagrams**.
            - Compute **phase fractions as a function of temperature** for fixed alloy compositions.
            - Visualize **composition-dependent properties** in higher-order alloy spaces using SymPlex maps.
            - Analyze **composition splitting** at selected temperatures.
            - Estimate **spinodal instability** using Hessian eigenvalues and eigenvectors.
            - Download generated figures and numerical data for further analysis.
            """
        )

    with st.container(border=True):
        st.subheader("How to use the interface")

        st.markdown(
            """
            Use the sidebar to navigate between modules. Each page asks for the alloy
            system, composition, temperature range, and analysis mode. The calculations
            are intended for rapid screening and visualization, and should be interpreted
            in the context of the underlying thermodynamic database and model assumptions.
            """
        )

with right:
    with st.container(border=True):
        st.subheader("Links")

        st.markdown(
            f"""
            - [Lab website]({LAB_URL})
            - [Developer profile]({PROFILE_URL})
            - [Source repository]({REPO_URL})
            - [Contact]({CONTACT_EMAIL})
            """
        )

    with st.container(border=True):
        st.subheader("Citation")

        st.markdown(
            """
            If you use RAPGen or figures generated from this interface, please cite the
            associated manuscript and thermodynamic framework.

            **Suggested citation**

            > P. Omprakash *et al.*, “Rapid phase-field prediction and visualization
            > of phase stability in multicomponent alloys,” manuscript in preparation.

            Replace this text with the final DOI/citation once available.
            """
        )

    with st.container(border=True):
        st.subheader("Copyright")

        st.markdown(
            """
            © 2026 M-Cube @ WashU. All rights reserved.

            This interface is provided for research, education, and visualization.
            Redistribution, commercial use, or reuse of generated datasets should follow
            the license terms of the associated repository and manuscript.
            """
        )

st.divider()

st.markdown(
    """
    **Note:** RAPGen is designed as an interactive front end to a thermodynamic
    prediction workflow. Results depend on the availability and quality of the
    underlying TDB files, binary interaction parameters, and phase models.
    """
)