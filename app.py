import os
from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports

ensure_project_imports()

pages = [
    st.Page("Home.py", title="Home", icon=":material/change_history:", default=True),
    st.Page("pages/1_SymPlex_Maps.py", title="SymPlex Maps", icon=":material/hub:"),
    st.Page(
        "pages/2_Phase_Fractions.py",
        title="Phase Fractions",
        icon=":material/stacked_bar_chart:",
    ),
    st.Page("pages/3_Phase_Diagrams.py", title="Phase Diagrams", icon=":material/timeline:"),
    st.Page("pages/4_Spinodal_Analysis.py", title="Spinodal Analysis", icon=":material/waves:"),
    st.Page(
        "pages/5_Alloy_System_Summary.py",
        title="Alloy System Summary",
        icon=":material/summarize:",
    ),
    st.Page(
        "pages/6_Inter_System_Comparison.py",
        title="Inter-System Comparison",
        icon=":material/balance:",
    ),
]

# The maintenance tool is deliberately absent from public navigation. Operators
# enable it explicitly in a local/admin deployment.
if os.environ.get("RAPTOR_ENABLE_TDB_MAINTENANCE", "").lower() in {"1", "true", "yes"}:
    pages.append(
        st.Page(
            "admin/TDB_Maintenance.py",
            title="TDB Maintenance",
            icon=":material/build:",
        )
    )

pg = st.navigation(pages)

pg.run()
