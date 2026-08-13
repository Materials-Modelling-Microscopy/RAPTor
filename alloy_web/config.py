from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

EXTERNAL_DIR = ROOT / "external"
PHASEFIELD_DIR = EXTERNAL_DIR / "Rapid_Phase_Field_Prediction"
SYMPLEX_DIR = EXTERNAL_DIR / "Symplex"

TDB_DIR = PHASEFIELD_DIR / "input/tdb"

# The 9 refractory elements every calculation adapter accepts. Lives here
# (not in ui.py) so it can be imported without pulling in streamlit.
AVAILABLE_ELEMENTS = [
    "Cr",
    "Hf",
    "Mo",
    "Nb",
    "Ta",
    "Ti",
    "V",
    "W",
    "Zr",
]


def ensure_project_imports() -> None:
    """
    Make sure the website repo root is visible to Streamlit pages.
    """

    paths = [
        ROOT,
        EXTERNAL_DIR,
        PHASEFIELD_DIR,
        SYMPLEX_DIR,
    ]

    for path in paths:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)