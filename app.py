from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports

ensure_project_imports()

pg = st.navigation(
    [
        st.Page("Home.py", title="Home", icon="🏠", default=True),
        st.Page("pages/1_SymPlex_Maps.py", title="SymPlex Maps", icon="🧭"),
        st.Page("pages/2_Phase_Fractions.py", title="Phase Fractions", icon="📊"),
        st.Page("pages/3_Phase_Diagrams.py", title="Phase Diagrams", icon="📈"),
        st.Page("pages/4_Spinodal_Analysis.py", title="Spinodal Analysis", icon="🌀"),
        st.Page(
            "pages/5_Alloy_System_Summary.py",
            title="Alloy System Summary",
            icon="🧪",
        ),
        st.Page(
            "pages/6_Inter_System_Comparison.py",
            title="Inter-System Comparison",
            icon="⚖️",
        ),
    ]
)

pg.run()
