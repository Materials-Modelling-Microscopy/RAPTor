import streamlit as st

from alloy_web.config import ensure_project_imports


ensure_project_imports()

st.set_page_config(
    page_title="Alloy Phase Diagram Predictor",
    layout="wide",
)

st.title("Rapid Alloy Phase-Field Generator (RAPGen)")

st.markdown(
    """
    Interactive web interface for phase-diagram and solid solution stability prediction of complex alloys.

    Use the sidebar to choose a module:

    - **SymPlex Maps**: Compressed visualizations of high-dimensional phase spaces.
    - **Phase Fractions**: Phase fractions vs. temperature for a fixed composition.
    - **Phase Diagrams**: Binary and ternary phase diagrams.
    """
)

st.info(
	"""
	Please cite these papers if you use the data from this website:
	- [1] Prediction of Phase Fields [To be updated]
	- [2] Cavin, J*, Omprakash, P*, Couet, A., & Mishra, R. (2025). SymPlex plots for visualizing properties in high-dimensional alloy spaces. Scripta Materialia, 268, 116840.
	- [3] Zhang, Z., Li, M., Cavin, J., Flores, K., & Mishra, R. (2022). 
	A fast and robust method for predicting the phase stability of refractory complex concentrated alloys using pairwise mixing enthalpy. Acta Materialia, 241, 118389.
	
	"""
)
