from pathlib import Path
import sys

import streamlit as st


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alloy_web.config import ensure_project_imports
from alloy_web.icons import brand_favicon, icon_markup


ensure_project_imports()

st.set_page_config(
    page_title="RAPGen",
    page_icon=brand_favicon(),
    layout="wide",
)


LAB_URL = "https://mcube.wustl.edu"
PROFILE_URL = "https://github.com/Pravanop/"
REPO_URL = "https://github.com/Pravanop/Phase_Field_Prediction_Visualization"
CONTACT_EMAIL = "mailto:rmishra@wustl.edu"


st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at 8% 4%, rgba(70, 111, 255, 0.10), transparent 28rem),
                radial-gradient(circle at 92% 16%, rgba(194, 74, 255, 0.09), transparent 26rem);
        }

        .block-container {
            max-width: 1120px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }

        .rapgen-hero {
            position: relative;
            overflow: hidden;
            padding: clamp(2rem, 5vw, 4.5rem);
            border-radius: 1.5rem;
            color: white;
            background:
                radial-gradient(circle at 88% 18%, rgba(255,255,255,0.20), transparent 12rem),
                linear-gradient(130deg, #10285f 0%, #3555c8 48%, #8a3fc0 100%);
            box-shadow: 0 24px 65px rgba(26, 48, 112, 0.24);
            margin-bottom: 1.4rem;
        }

        .rapgen-brand-mark {
            position: absolute;
            z-index: 1;
            top: clamp(1.5rem, 4vw, 3rem);
            right: clamp(1.5rem, 4vw, 3rem);
            display: grid;
            place-items: center;
            width: clamp(4rem, 9vw, 6.4rem);
            height: clamp(4rem, 9vw, 6.4rem);
            border: 1px solid rgba(255,255,255,0.28);
            border-radius: 1.35rem;
            color: white;
            background: rgba(255,255,255,0.11);
            backdrop-filter: blur(8px);
        }

        .rapgen-hero::after {
            content: "";
            position: absolute;
            width: 18rem;
            height: 18rem;
            right: -5rem;
            bottom: -9rem;
            border: 1px solid rgba(255,255,255,0.28);
            border-radius: 50%;
            box-shadow: 0 0 0 2.5rem rgba(255,255,255,0.05),
                        0 0 0 5rem rgba(255,255,255,0.035);
        }

        .rapgen-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.72rem;
            border: 1px solid rgba(255,255,255,0.34);
            background: rgba(255,255,255,0.12);
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .rapgen-hero h1 {
            max-width: 760px;
            margin: 1.15rem 0 0.9rem;
            font-size: clamp(2.5rem, 6vw, 4.6rem);
            line-height: 0.98;
            letter-spacing: -0.055em;
            color: white;
        }

        .rapgen-hero p {
            max-width: 730px;
            margin: 0;
            color: rgba(255,255,255,0.88);
            font-size: clamp(1rem, 2vw, 1.2rem);
            line-height: 1.65;
        }

        .hero-pills, .tool-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
        }

        .hero-pills { margin-top: 1.7rem; }

        .hero-pill {
            padding: 0.45rem 0.72rem;
            border-radius: 0.55rem;
            background: rgba(255,255,255,0.12);
            color: rgba(255,255,255,0.92);
            font-size: 0.82rem;
            font-weight: 600;
        }

        .workflow-strip {
            display: flex;
            align-items: center;
            justify-content: center;
            flex-wrap: wrap;
            gap: 0.75rem;
            padding: 1rem 1.2rem;
            margin: 0 0 3rem;
            border: 1px solid rgba(105, 120, 170, 0.18);
            border-radius: 0.9rem;
            background: rgba(255,255,255,0.64);
            color: #34405f;
            font-size: 0.9rem;
            font-weight: 650;
            backdrop-filter: blur(8px);
        }

        .workflow-arrow { color: #8a3fc0; font-size: 1.15rem; }

        .section-kicker {
            margin-bottom: 0.2rem;
            color: #5b67b8;
            font-size: 0.75rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .section-title {
            margin: 0 0 0.55rem;
            font-size: clamp(1.7rem, 3vw, 2.35rem);
            letter-spacing: -0.035em;
        }

        .section-copy {
            max-width: 760px;
            margin: 0 0 1.5rem;
            color: inherit;
            opacity: 0.64;
            font-size: 1rem;
            line-height: 1.6;
        }

        .tool-header {
            position: relative;
            margin: -0.15rem -0.15rem 0.9rem;
            padding: 1.15rem 1.25rem;
            border-radius: 0.85rem;
            color: white;
        }

        .tool-icon {
            position: absolute;
            top: 1rem;
            right: 1rem;
            display: grid;
            place-items: center;
            width: 2.75rem;
            height: 2.75rem;
            border: 1px solid rgba(255,255,255,0.25);
            border-radius: 0.72rem;
            color: white;
            background: rgba(255,255,255,0.12);
        }

        .tool-header h3, .tool-question { padding-right: 3.25rem; }

        .tool-header.summary { background: linear-gradient(115deg, #6d3cc4, #a64bc7); }
        .tool-header.compare { background: linear-gradient(115deg, #344bb2, #c14e8a); }
        .tool-header.symplex { background: linear-gradient(115deg, #1c63b7, #328fc4); }
        .tool-header.fractions { background: linear-gradient(115deg, #167f73, #27a87d); }
        .tool-header.diagrams { background: linear-gradient(115deg, #c45929, #dc8731); }
        .tool-header.spinodal { background: linear-gradient(115deg, #b72f5e, #dc4b7c); }
        .tool-header.pathways { background: linear-gradient(115deg, #4f3ba7, #2f83ad); }

        .tool-number {
            opacity: 0.76;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .tool-header h3 {
            margin: 0.18rem 0 0.15rem;
            color: white;
            font-size: 1.45rem;
            letter-spacing: -0.025em;
        }

        .tool-question {
            margin: 0;
            color: rgba(255,255,255,0.88);
            font-size: 0.94rem;
            font-weight: 550;
        }

        .tool-description {
            color: inherit;
            opacity: 0.72;
            font-size: 0.97rem;
            line-height: 1.62;
            margin-bottom: 0.9rem;
        }

        .tool-tag {
            padding: 0.35rem 0.58rem;
            border-radius: 999px;
            background: rgba(112, 128, 190, 0.14);
            color: inherit;
            opacity: 0.84;
            font-size: 0.76rem;
            font-weight: 650;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(103, 116, 162, 0.20);
            border-radius: 1.1rem;
            background: rgba(255,255,255,0.76);
            box-shadow: 0 12px 32px rgba(32, 48, 92, 0.07);
        }

        div[data-testid="stPageLink"] a {
            border-radius: 0.65rem;
            font-weight: 700;
        }

        .method-note {
            margin: 3rem 0 1rem;
            padding: 1.2rem 1.35rem;
            border-left: 4px solid #536bd4;
            border-radius: 0.35rem 0.85rem 0.85rem 0.35rem;
            background: rgba(74, 98, 201, 0.08);
            color: inherit;
            line-height: 1.6;
        }

        .rapgen-footer {
            margin-top: 2.5rem;
            padding: 1.4rem 0 0.3rem;
            border-top: 1px solid rgba(100, 112, 150, 0.18);
            color: inherit;
            opacity: 0.66;
            font-size: 1rem;
            line-height: 1.8;
        }

        .rapgen-footer a {
            color: #FFFFFF;
            text-decoration: none;
            font-weight: 650;
            margin-right: 1.5rem;
        }

        @media (max-width: 700px) {
            .rapgen-hero { border-radius: 1rem; }
            .rapgen-hero h1 { font-size: 2.6rem; }
            .workflow-strip { justify-content: flex-start; }
            .rapgen-brand-mark { position: relative; top: auto; right: auto; margin-bottom: 1.2rem; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    f"""
    <section class="rapgen-hero">
        <div class="rapgen-brand-mark">{icon_markup("brand", 62)}</div>
        <div class="rapgen-eyebrow">RAPGen · First-principle based alloy thermodynamics</div>
        <h1>Rapid Alloy Phase-field GENerator</h1>
        <p>
            Explore solid solution formation, when they become miscible, which
            intermetallics compete, and how instability develops across composition
            and temperature—all from one place.
        </p>
        <div class="hero-pills">
            <span class="hero-pill">Multi-Principal Element Alloys</span>
            <span class="hero-pill">Equilibrium Thermodynamics</span>
            <span class="hero-pill">Alloy & Composition-space screening</span>
            <span class="hero-pill">Downloadable results and plots</span>
        </div>
    </section>
    <div class="workflow-strip">
        <span>① Choose an alloy system</span>
        <span class="workflow-arrow">→</span>
        <span>② Select the scientific question</span>
        <span class="workflow-arrow">→</span>
        <span>③ Calculate, compare, and export</span>
    </div>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <div class="section-kicker">Analysis workspace</div>
    <h2 class="section-title">Choose the question you want to answer</h2>
    <p class="section-copy">
        Each tool is built around a different thermodynamic question. Start with the
        system summary for orientation, then move into composition, temperature, phase
        boundary, or stability detail as your investigation narrows.
    </p>
    """,
    unsafe_allow_html=True,
)


TOOLS = [
    {
        "number": "Recommended starting point",
        "class": "summary",
        "title": "Alloy System Summary",
        "question": "What is the thermodynamic character of this alloy system?",
        "description": (
            "Build a system-level briefing across the selected alloy and every equimolar "
            "subsystem. Compare miscibility temperatures, estimate the percentage miscible "
            "region, review competing intermetallics, and inspect binary interaction parameters."
        ),
        "tags": ["PMR", "Miscibility temperature", "Subsystems", "Intermetallics", "Interactions"],
        "page": "pages/5_Alloy_System_Summary.py",
        "link": "Open Alloy System Summary",
        "icon_name": "summary",
        "icon": ":material/summarize:",
    },
    {
        "number": "Candidate screening",
        "class": "compare",
        "title": "Inter-System Comparison",
        "question": "Which alloy systems best balance the stability properties I care about?",
        "description": (
            "Expand an element pool into every binary through quinary candidate at one selected "
            "order. Rank directional thermodynamic properties, inspect the non-directional "
            "path-burden landscape, identify Pareto-optimal tradeoffs, and reuse settings-aware "
            "SQLite results when the same systems are compared again."
        ),
        "tags": ["Candidate ranking", "Pareto set", "Path-burden landscape", "SQLite cache"],
        "page": "pages/6_Inter_System_Comparison.py",
        "link": "Open Inter-System Comparison",
        "icon_name": "compare",
        "icon": ":material/balance:",
    },
    {
        "number": "Processing-order sensitivity",
        "class": "pathways",
        "title": "Processing Pathways",
        "question": "How strongly does the thermodynamic burden depend on the alloying sequence?",
        "description": (
            "Enumerate unique sequential alloying routes to one target composition. Compare the "
            "integrated BCC energy above the equilibrium hull, quantify path dependence with the "
            "variance between routes, and inspect equilibrium phase fractions along each path."
        ),
        "tags": ["Sequential alloying", "Path burden", "Path variance", "Phase fractions"],
        "page": "pages/7_Processing_Pathways.py",
        "link": "Open Processing Pathways",
        "icon_name": "diagram",
        "icon": ":material/route:",
    },
    {
        "number": "Composition-space map",
        "class": "symplex",
        "title": "SymPlex Maps",
        "question": "Where in a quaternary or quinary composition space does a property change?",
        "description": (
            "Screen hundreds of high-symmetry compositions at one temperature. Map solid-solution "
            "phase fraction, BCC energy above the equilibrium hull, phase count, or minimum spinodal "
            "eigenvalue without inspecting compositions one at a time."
        ),
        "tags": ["4–5 components", "SPSS fraction", "BCC energy above hull", "Phase count", "Spinodal eigenvalue"],
        "page": "pages/1_SymPlex_Maps.py",
        "link": "Open SymPlex Maps",
        "icon_name": "symplex",
        "icon": ":material/hub:",
    },
    {
        "number": "Temperature and partitioning",
        "class": "fractions",
        "title": "Phase Fractions",
        "question": "Which phases are present, how much is present, and where do the elements partition?",
        "description": (
            "Follow equilibrium phase fractions through temperature for a fixed composition, or "
            "compare phase compositions at selected temperatures. The temperature profile also tracks "
            "homogeneous BCC energy above the equilibrium hull and its metastable-to-stable crossings."
        ),
        "tags": ["Temperature profiles", "BCC stability", "Phase amounts", "Composition splitting", "CSV export"],
        "page": "pages/2_Phase_Fractions.py",
        "link": "Open Phase Fractions",
        "icon_name": "fractions",
        "icon": ":material/stacked_bar_chart:",
    },
    {
        "number": "Phase-boundary detail",
        "class": "diagrams",
        "title": "Phase Diagrams",
        "question": "Where are the equilibrium phase boundaries in binary and ternary systems?",
        "description": (
            "Generate binary temperature–composition diagrams or ternary isothermal sections "
            "directly from the available TDB. Include intermetallic phases to reveal solvus lines, "
            "multiphase fields, and composition ranges where ordered compounds compete."
        ),
        "tags": ["Binary T–x", "Ternary isotherms", "Tie lines", "Intermetallic phases"],
        "page": "pages/3_Phase_Diagrams.py",
        "link": "Open Phase Diagrams",
        "icon_name": "diagram",
        "icon": ":material/timeline:",
    },
    {
        "number": "Local stability",
        "class": "spinodal",
        "title": "Spinodal Analysis",
        "question": "When does a homogeneous solution become locally unstable, and how will it separate?",
        "description": (
            "Track Hessian eigenvalues with temperature, estimate the spinodal crossing, and inspect "
            "the soft-mode eigenvector. The mode groups elements by their tendency to enrich or "
            "deplete during the earliest stage of spinodal decomposition."
        ),
        "tags": ["Hessian spectrum", "Spinodal temperature", "Soft mode", "Decomposition direction"],
        "page": "pages/4_Spinodal_Analysis.py",
        "link": "Open Spinodal Analysis",
        "icon_name": "spinodal",
        "icon": ":material/waves:",
    },
]


for tool in TOOLS:
    with st.container(border=True):
        tags = "".join(f'<span class="tool-tag">{tag}</span>' for tag in tool["tags"])
        icon = icon_markup(tool["icon_name"], 30)
        st.markdown(
            f"""
            <div class="tool-header {tool['class']}">
                <div class="tool-icon">{icon}</div>
                <div class="tool-number">{tool['number']}</div>
                <h3>{tool['title']}</h3>
                <p class="tool-question">{tool['question']}</p>
            </div>
            <p class="tool-description">{tool['description']}</p>
            <div class="tool-tags">{tags}</div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link(tool["page"], label=tool["link"], icon=tool["icon"])


st.markdown(
    """
    <div class="method-note">
        <strong>DISCLAIMER: Interpretation matters.</strong> RAPGen is designed for rapid screening and
        scientific comparison. Every result inherits the assumptions, phase models, and data
        coverage of its thermodynamic database; use the downloadable numerical output when a
        decision needs closer validation.
    </div>
    """,
    unsafe_allow_html=True,
)


with st.expander("Citation and research use"):
    st.markdown(
        """
        If you use RAPGen or figures generated from this interface, please cite the following works accordingly:
        
        Thermodyanamic framework:
        > Omprakash et al. First-principles-based Prediction of Phase Fields: Part I. Binary and Ternary Refractory Alloys, Manuscript under preparation.
        
        > Omprakash et al. First-principles-based Prediction of Phase Fields: Part II. Solid Solution Tunability in Refractory Complex Concentrated Alloys, Manuscript under preparation

        SymPlex Maps:
        > Cavin, John, Pravan Omprakash, Adrien Couet, and Rohan Mishra. "SymPlex plots for visualizing properties in high-dimensional alloy spaces." Scripta Materialia 268 (2025): 116840.
        
        
        PyCalphad:
        > Otis, Richard, and Zi-Kui Liu. "pycalphad: CALPHAD-based Computational Thermodynamics in Python." In Zentropy, pp. 373-392. Jenny Stanford Publishing, 2024.
        
        Spinodal Analysis:
        > Omprakash et al. Thermodynamic design rules for tuning MPEA microstructures via spinodal decompositions, Manuscript under preparation
        
        Data:
        > Dinsdale, Alan T. "SGTE data for pure elements." Calphad 15, no. 4 (1991): 317-425.
        
        > Jain, Anubhav, Shyue Ping Ong, Geoffroy Hautier, Wei Chen, William Davidson Richards, Stephen Dacek, Shreyas Cholia et al. "Commentary: The Materials Project: A materials genome approach to accelerating materials innovation." APL materials 1, no. 1 (2013).
        
        """
    )

with st.expander("Additional Reading"):
    st.markdown(
        """
        These works provided the foundation for the related thermodynamic framework used in this interface:

        > Zhang, Zhaohan, Mu Li, John Cavin, Katharine Flores, and Rohan Mishra. "A fast and robust method for predicting the phase stability of refractory complex concentrated alloys using pairwise mixing enthalpy." Acta Materialia 241 (2022): 118389.
        
        > Chen, Wei, Antoine Hilhorst, Georgios Bokas, Stéphane Gorsse, Pascal J. Jacques, and Geoffroy Hautier. "A map of single-phase high-entropy alloys." Nature Communications 14, no. 1 (2023): 2856.
        
        > Bokas, Georgios B., Wei Chen, Antoine Hilhorst, Pascal J. Jacques, Stéphane Gorsse, and Geoffroy Hautier. "Unveiling the thermodynamic driving forces for high entropy alloys formation through big data ab initio analysis." Scripta Materialia 202 (2021): 114000.
        
        > Kadirvel, Kamalnath, Shalini Roy Koneru, and Yunzhi Wang. "Exploration of spinodal decomposition in multi-principal element alloys (MPEAs) using CALPHAD modeling." Scripta Materialia 214 (2022): 114657.
        
        > Cavin, John, and Rohan Mishra. "Equilibrium phase diagrams of isostructural and heterostructural two-dimensional alloys from first principles." Iscience 25, no. 4 (2022).

        """
    )

st.markdown(
    f"""
    <footer class="rapgen-footer">
        <div>
            <a href="{LAB_URL}" target="_blank">M-Cube @ WashU</a>
            <a href="{PROFILE_URL}" target="_blank">Developer</a>
            <a href="{REPO_URL}" target="_blank">Source repository</a>
            <a href="{CONTACT_EMAIL}">Contact</a>
        </div>
        <div>© 2026 M-Cube @ WashU · Research and education interface</div>
    </footer>
    """,
    unsafe_allow_html=True,
)
