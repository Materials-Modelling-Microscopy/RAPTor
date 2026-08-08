# RAPTor calculation engine

This directory contains the numerical routines and calculation inputs behind RAPTor. It can be used without Streamlit. The web interface imports the modules directly under this directory; those active paths are the ones documented below.

These modules are research-code interfaces rather than a stable public API. For validated inputs and consistent result objects, start with the functions in [`alloy_web/adapters/`](../../alloy_web/README.md). Call the routines here directly when a workflow needs lower-level control.

## Directory map

| Path | What it provides |
| --- | --- |
| `phase_diagram_generators/symplex_data_generator.py` | Batched composition-grid properties for quaternary and quinary SymPlex maps. |
| `phase_diagram_generators/energy_above_hull.py` | Homogeneous BCC_A2 Gibbs energy, equilibrium hull comparison, threshold detection, and plotting. |
| `phase_diagram_generators/spinodal_predictor.py` | Interaction-data loading and constrained-composition Hessian calculations. |
| `phase_diagram_generators/spinodal_analysis.py` | Temperature spectra, zero-crossing estimates, soft modes, interpretation, and plots. |
| `phase_diagram_analysis/temperature_profile_per_composition.py` | Phase fractions and BCC energy above hull versus temperature at one composition. |
| `phase_diagram_analysis/composition_profile_per_temperature.py` | Equilibrium phase-composition splitting at selected temperatures. |
| `phase_diagram_analysis/phase_diagram_plotters.py` | Binary temperature-composition and isothermal ternary diagrams. |
| `input/tdb/` | Read-only thermodynamic database inputs. |
| `input/spinodal/binary_interactions.json` | Binary interaction parameters used by the spinodal model. |
| `input/DFT_calculated/`, `input/Empirical_database/`, `input/MP_database/` | Supporting calculated and empirical datasets used by project workflows. |
| `phase_diagram_generators/mol_grid_data/` | Composition grids used by the SymPlex generator. |

## Recommended entry points

The internal adapters provide input validation and package DataFrames and figures into dataclasses:

| Task | Adapter function |
| --- | --- |
| SymPlex grid and plot | `run_symplex_prediction` |
| Phase fractions and BCC energy above hull versus temperature | `run_phase_fraction_temperature_prediction` |
| Phase-composition splitting | `run_composition_splitting_prediction` |
| Binary or ternary phase diagram | `run_phase_diagram_prediction` |
| Spinodal spectrum and mode | `run_spinodal_analysis` |
| Whole-system summary | `run_alloy_system_summary` |
| Combination ranking and Pareto analysis | `run_inter_system_comparison` |

See [`alloy_web/README.md`](../../alloy_web/README.md) for signatures and returned data.

## Direct calculation recipes

Run these from the repository root. The bootstrap call adds the source checkout's
engine directories to Python's import path; Streamlit performs the same setup at
application startup.

### Phase fractions at a fixed composition

```python
from alloy_web.config import ensure_project_imports

ensure_project_imports()

from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.temperature_profile_per_composition import (
    generate_phase_fraction_temperature_profile,
)

(
    phase_data,
    phase_figure,
    hull_data,
    hull_figure,
    metastable_temperature,
    stable_temperature,
) = generate_phase_fraction_temperature_profile(
    composition="Cr-Ta-Ti-W",
    mol_ratio=[0.25, 0.25, 0.25, 0.25],
    input_file_path="external/Rapid_Phase_Field_Prediction/input/tdb",
    temp_range=(300, 3000, 50),
)
```

`phase_data` contains calculated phase fractions over the requested grid. `hull_data` contains homogeneous BCC_A2 energy above the equilibrium hull over the same temperature range.

### Binary phase diagram

```python
from alloy_web.config import ensure_project_imports

ensure_project_imports()

from external.Rapid_Phase_Field_Prediction.phase_diagram_analysis.phase_diagram_plotters import (
    generate_binary_phase_diagram,
)

figure, axis = generate_binary_phase_diagram(
    composition="Cr-W",
    tdb_dir="external/Rapid_Phase_Field_Prediction/input/tdb",
    include_intermetallics=True,
    temperature_min=300,
    temperature_max=3000,
    temperature_step=10,
    composition_step=0.02,
)
```

### Spinodal data without plotting a web page

```python
from alloy_web.config import ensure_project_imports

ensure_project_imports()

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_predictor import (
    load_interaction_data,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_analysis import (
    compute_spinodal_vs_temperature,
    estimate_spinodal_temperature,
)

interactions = load_interaction_data(
    "external/Rapid_Phase_Field_Prediction/input/spinodal/"
    "binary_interactions.json"
)

spectrum = compute_spinodal_vs_temperature(
    composition=["Cr", "Ta", "Ti", "W"],
    mol_ratio=[0.25, 0.25, 0.25, 0.25],
    lattice="BCC",
    interaction_data=interactions,
    temperature_min=300,
    temperature_max=3000,
    temperature_step=25,
)

spinodal_temperature = estimate_spinodal_temperature(spectrum)
```

### SymPlex property data

```python
from alloy_web.config import ensure_project_imports

ensure_project_imports()

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.symplex_data_generator import (
    symplexDataGenerator,
)

data = symplexDataGenerator(
    alloy_system=["Cr", "Ta", "Ti", "W"],
    temperature=1500,
    property="BCC Energy Above Hull",
).generate()
```

Supported web-facing property names are `SPSS Phase Fraction`, `BCC Energy Above Hull`, `Number of Phases`, and `Minimum Spinodal Eigenvalue`.

## Thermodynamic database selection

Most routines resolve a TDB using a composition string such as `Cr-Ta-Ti-W`. In the supplied collection, filename order can matter. Check `input/tdb/` and use the element order represented by the available file.

The current RAPTor workflows read TDB files but do not modify them. Treat them as immutable scientific inputs. If you add a database, preserve its provenance and licensing information outside generated outputs. Do not store calculation caches in `input/tdb/`.

## Outputs and interpretation

| Output | Unit or meaning |
| --- | --- |
| Temperature | K |
| Phase fraction | Fraction of total equilibrium material |
| BCC energy above hull | meV/atom relative to equilibrium Gibbs energy |
| Spinodal eigenvalue | Curvature from the constrained-composition Gibbs Hessian; sign and units follow the implemented model |
| Spinodal mode | Relative elemental amplitudes in the minimum-eigenvalue eigenvector |

A temperature or composition grid is a numerical sampling choice, not metadata. Preserve the grid, enabled phases, database identity, and source revision with exported results.

## Performance guidance

- Increase temperature or composition step sizes for exploratory work, then refine around transitions.
- Prefer the batched SymPlex generator over repeated scalar equilibrium calls.
- Reuse adapter results and the inter-system SQLite cache when settings and source signatures match.
- Close or reuse Matplotlib figures during large batch studies to avoid unnecessary memory growth.
- Validate coarse-grid transition temperatures with a finer local scan before reporting them.

## Extending the engine

Keep scientific computation in this directory, input validation and result normalization in `alloy_web/adapters/`, and Streamlit rendering in `pages/`. This separation lets scripts and the website share one calculation path instead of maintaining duplicate implementations.
