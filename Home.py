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
            margin: -0.15rem -0.15rem 0.9rem;
            padding: 1.15rem 1.25rem;
            border-radius: 0.85rem;
            color: white;
        }

        .tool-header.summary { background: linear-gradient(115deg, #6d3cc4, #a64bc7); }
        .tool-header.compare { background: linear-gradient(115deg, #344bb2, #c14e8a); }
        .tool-header.symplex { background: linear-gradient(115deg, #1c63b7, #328fc4); }
        .tool-header.fractions { background: linear-gradient(115deg, #167f73, #27a87d); }
        .tool-header.diagrams { background: linear-gradient(115deg, #c45929, #dc8731); }
        .tool-header.spinodal { background: linear-gradient(115deg, #b72f5e, #dc4b7c); }

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
            font-size: 0.83rem;
            line-height: 1.8;
        }

        .rapgen-footer a {
            color: #5264bf;
            text-decoration: none;
            font-weight: 650;
            margin-right: 1rem;
        }

        @media (max-width: 700px) {
            .rapgen-hero { border-radius: 1rem; }
            .rapgen-hero h1 { font-size: 2.6rem; }
            .workflow-strip { justify-content: flex-start; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <section class="rapgen-hero">
        <div class="rapgen-eyebrow">🧪 RAPGen · First-principle based alloy thermodynamics </div>
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
        "icon": "🧪",
    },
    {
        "number": "Candidate screening",
        "class": "compare",
        "title": "Inter-System Comparison",
        "question": "Which alloy systems best balance the stability properties I care about?",
        "description": (
            "Expand an element pool into every binary through quinary candidate at one selected "
            "order. Rank six thermodynamic properties, identify Pareto-optimal tradeoffs, and "
            "reuse settings-aware SQLite results when the same systems are compared again."
        ),
        "tags": ["Candidate ranking", "Pareto set", "Six properties", "SQLite cache"],
        "page": "pages/6_Inter_System_Comparison.py",
        "link": "Open Inter-System Comparison",
        "icon": "⚖️",
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
        "icon": "🧭",
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
        "icon": "📊",
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
        "icon": "📈",
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
        "icon": "🌀",
    },
]


for tool in TOOLS:
    with st.container(border=True):
        tags = "".join(f'<span class="tool-tag">{tag}</span>' for tag in tool["tags"])
        st.markdown(
            f"""
            <div class="tool-header {tool['class']}">
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
        <strong>Interpretation matters.</strong> RAPGen is designed for rapid screening and
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
        If you use RAPGen or figures generated from this interface, please cite the
        associated manuscript and thermodynamic framework.

        > P. Omprakash *et al.*, “Rapid phase-field prediction and visualization
        > of phase stability in multicomponent alloys,” manuscript in preparation.

        Replace this text with the final DOI and citation once available.
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
