"""
RAPTor: CALPHAD-based phase stability predictions for multi-principal-element
refractory alloys.

This is a thin, stable façade over the calculation engine in
``external/Rapid_Phase_Field_Prediction`` and its validated wrappers in
``alloy_web/adapters``. Import from here rather than from those internal
modules directly — their layout is free to change between releases; this
namespace is not.

    import raptor_alloys as rap

    result = rap.run_phase_diagram_prediction(
        alloy_system=["Cr", "W"],
        tdb_dir=rap.TDB_DIR,
    )
    result.figure.savefig("Cr-W.png")

Every function accepts elements in any order and validates its own inputs;
none of them require Streamlit or any of the optional ``[web]``/
``[assistant]`` extras.
"""

from __future__ import annotations

from alloy_web.config import AVAILABLE_ELEMENTS, TDB_DIR, ensure_project_imports

# Two engine modules resolve sibling imports relative to the engine's own
# root (e.g. `from phase_diagram_generators.spinodal_predictor import ...`)
# rather than as fully qualified package paths, so that directory must be on
# sys.path before anything below is imported — regardless of whether this
# package was installed normally or with `pip install -e .`.
ensure_project_imports()

from alloy_web.adapters.alloy_summary_adapter import (
    AlloySystemSummaryResult,
    run_alloy_system_summary,
)
from alloy_web.adapters.inter_system_adapter import (
    InterSystemComparisonResult,
    run_inter_system_comparison,
)
from alloy_web.adapters.pathway_adapter import (
    PathwayAnalysisResult,
    run_pathway_analysis,
)
from alloy_web.adapters.phasefield_adapter import (
    CompositionSplittingResult,
    PhaseDiagramResult,
    PhaseFractionTemperatureResult,
    run_composition_splitting_prediction,
    run_phase_diagram_prediction,
    run_phase_fraction_temperature_prediction,
)
from alloy_web.adapters.spinodal_adapter import (
    SpinodalPageResult,
    run_spinodal_analysis,
)
from alloy_web.adapters.symplex_adapter import (
    SymplexPredictionResult,
    run_symplex_prediction,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AVAILABLE_ELEMENTS",
    "TDB_DIR",
    # Alloy system summary
    "run_alloy_system_summary",
    "AlloySystemSummaryResult",
    # Inter-system comparison
    "run_inter_system_comparison",
    "InterSystemComparisonResult",
    # Processing pathways
    "run_pathway_analysis",
    "PathwayAnalysisResult",
    # Phase fractions / composition splitting / phase diagrams
    "run_phase_fraction_temperature_prediction",
    "PhaseFractionTemperatureResult",
    "run_composition_splitting_prediction",
    "CompositionSplittingResult",
    "run_phase_diagram_prediction",
    "PhaseDiagramResult",
    # Spinodal analysis
    "run_spinodal_analysis",
    "SpinodalPageResult",
    # SymPlex maps
    "run_symplex_prediction",
    "SymplexPredictionResult",
]
