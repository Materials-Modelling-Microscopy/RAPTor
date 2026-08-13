# RAPTor web integration layer

`alloy_web` connects the calculation engine to Streamlit. Its adapters are also the most convenient way to run RAPTor calculations from a Python script because they validate inputs and return named result objects containing DataFrames, figures, metadata, and serialization helpers.

This is an internal integration interface, not yet a stable public API. Scripts intended for long-term reproduction should record the repository commit they use.

## What belongs here

| Path | Responsibility |
| --- | --- |
| `adapters/` | Validate inputs, call one shared numerical implementation, and normalize results for Python or UI use. |
| `config.py` | Resolve repository, calculation-engine, SymPlex, and TDB paths. |
| `ui.py` | Reusable Streamlit controls and page presentation helpers. |
| `icons.py` and `assets/` | RAPTor branding and page icons. |
| `data/` | Small application datasets and generated local caches. |

Scientific algorithms should live in `external/Rapid_Phase_Field_Prediction/`, not in Streamlit pages or CSS/UI helpers.

## Adapter catalog

| Module | Main call | Returned information |
| --- | --- | --- |
| `symplex_adapter.py` | `run_symplex_prediction(alloy_system, temperature, constraint_element, property_name)` | Property data dictionary and SymPlex figure. |
| `phasefield_adapter.py` | `run_phase_fraction_temperature_prediction(...)` | Phase-fraction DataFrame/figure, energy-above-hull DataFrame/figure, and threshold temperatures. |
| `phasefield_adapter.py` | `run_composition_splitting_prediction(...)` | Phase-composition DataFrame and figure for each requested temperature. |
| `phasefield_adapter.py` | `run_phase_diagram_prediction(...)` | Binary or ternary figure and underlying plotting objects. |
| `spinodal_adapter.py` | `run_spinodal_analysis(...)` | Eigenvalue spectrum, crossing temperature, soft mode, interpretation, and figures. |
| `alloy_summary_adapter.py` | `run_alloy_system_summary(...)` | System and subsystem miscibility, PMR, interaction data, and considered intermetallics. |
| `inter_system_adapter.py` | `run_inter_system_comparison(...)` | Ranked systems, selected metrics, Pareto membership, cache statistics, and timings. |
| `pathway_adapter.py` | `run_pathway_analysis(...)` | Integrated burden for every unique processing path, energy and equilibrium phase fractions along each path, and system-level path dependence. |
| `experimental_adapter.py` | `load_experimental_evidence(...)` | Citation-linked experimental records matching an alloy system. |

The function definitions and dataclasses in each adapter are the authoritative description of current arguments and fields.

## Typical script pattern

```python
from alloy_web.config import TDB_DIR, ensure_project_imports

ensure_project_imports()

from alloy_web.adapters.phasefield_adapter import run_phase_diagram_prediction

result = run_phase_diagram_prediction(
    alloy_system=["Cr", "W"],
    tdb_dir=TDB_DIR,
    include_intermetallics=True,
    temperature_min=300,
    temperature_max=3000,
    temperature_step=10,
    composition_step=0.02,
)

result.figure.savefig("Cr-W_phase_diagram.png", dpi=300, bbox_inches="tight")
```

Adapters return ordinary Python objects. DataFrames can be exported with `to_csv`; Matplotlib figures can be saved with `savefig`; several result classes also provide `to_csv_bytes`, `to_png_bytes`, or `to_pickle_bytes` for the web download controls.

## Data and cache behavior

- `config.TDB_DIR` points to the read-only TDB input collection.
- `data/inter_system_metrics.sqlite3` is a generated cache. Cached values are keyed by system, metric settings, and source signatures so changed inputs can be recalculated.
- `data/experimental_citations.json` is a curated application dataset. Keep the citation fields attached to each experimental record when transforming or displaying it.
- The Alloy System Summary reads experimental evidence; it does not write back to the Alloy Assistant database or to TDB files.

## Adding a calculation to the website

1. Implement or reuse the numerical routine in the calculation engine.
2. Add a thin adapter that validates inputs and returns a named dataclass.
3. Test the adapter independently of Streamlit.
4. Let the page handle only controls, progress, display, and downloads.

Following this path keeps notebook/script users and web users on the same scientific implementation.
