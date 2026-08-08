# RAPTor

**Rapid Alloy Phase-field generaTOR** is research software for exploring phase stability in multi-principal-element and refractory alloy systems. It combines thermodynamic equilibrium calculations, spinodal analysis, high-dimensional SymPlex maps, phase-diagram plotting, system-level summaries, and experimental evidence in one source repository.

The Streamlit website is one way to use RAPTor. The numerical routines and validated adapter functions can also be run directly from Python for scripted studies, batch calculations, and downstream analysis. Access the website here: https://rapgen.streamlit.app

> **Research-code status:** RAPTor is currently used from a source checkout. It is not yet distributed as an installable Python package, and the internal Python interfaces are not a versioned public API. The examples below use the same calculation paths as the web interface, but function signatures may evolve while the package boundary is formalized.

## What RAPTor can calculate

| Capability | Main outputs | Implementation |
| --- | --- | --- |
| SymPlex property maps | SPSS phase fraction, BCC energy above hull, phase count, minimum spinodal eigenvalue | `external/Rapid_Phase_Field_Prediction/phase_diagram_generators/` and `external/Symplex/` |
| Composition-specific temperature profiles | Phase fractions and BCC energy above hull versus temperature | `external/Rapid_Phase_Field_Prediction/phase_diagram_analysis/` |
| Composition splitting | Equilibrium phase compositions at selected temperatures | `external/Rapid_Phase_Field_Prediction/phase_diagram_analysis/` |
| Phase diagrams | Binary temperature-composition and isothermal ternary diagrams | `external/Rapid_Phase_Field_Prediction/phase_diagram_analysis/` |
| Spinodal stability | Hessian eigenvalue spectra, spinodal crossing temperature, and soft eigenmodes | `external/Rapid_Phase_Field_Prediction/phase_diagram_generators/` |
| Alloy-system summaries | Miscibility temperature, percentage miscible region (PMR), subsystem behavior, and considered intermetallics | `alloy_web/adapters/alloy_summary_adapter.py` |
| Inter-system comparison | Ranking, Pareto filtering, and a local SQLite calculation cache | `alloy_web/adapters/inter_system_adapter.py` |
| Experimental and literature evidence | Provenance-preserving structured records, document retrieval, and reviewed queries | `alloy_assistant/` |

The current thermodynamic calculations focus on the BCC_A2, FCC_A1, and HCP_A3 solid-solution phases represented in the supplied thermodynamic databases, together with applicable intermetallic phases.

## Quick start

Python 3.11 is the supported runtime

```bash
git clone https://github.com/Pravanop/Phase_Field_Prediction_Visualization.git
cd Phase_Field_Prediction_Visualization

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Repository guide

| Path | Role |
| --- | --- |
| [`external/Rapid_Phase_Field_Prediction/`](external/Rapid_Phase_Field_Prediction/) | Thermodynamic, phase-field, spinodal, and phase-diagram calculation engine. See its [calculation guide](external/Rapid_Phase_Field_Prediction/README.md). |
| [`external/Symplex/`](external/Symplex/) | High-dimensional simplex decomposition and plotting. See the [SymPlex guide](external/Symplex/README.md). |
| [`alloy_web/`](alloy_web/) | Validation and result adapters shared by the pages, plus UI components. See the [adapter guide](alloy_web/README.md). |
| [`pages/`](pages/) | Streamlit presentation layer. Scientific calculations should remain outside this directory. |
| [`alloy_assistant/`](alloy_assistant/) | Local DuckDB knowledge workspace, ingestion, reviewed queries, retrieval, and citation-preserving evidence. See the [assistant guide](alloy_assistant/README.md). |
| [`tests/`](tests/) | Tests for web adapters and cross-layer behavior. |

## Using the calculations without Streamlit

Run these examples from the repository root after activating the environment. The `alloy_web.adapters` functions are convenient internal entry points: they perform the same input checks and return the same structured results used by the website.

### Phase fractions and BCC energy above hull

```python
from alloy_web.config import TDB_DIR, ensure_project_imports

ensure_project_imports()

from alloy_web.adapters.phasefield_adapter import (
    run_phase_fraction_temperature_prediction,
)

result = run_phase_fraction_temperature_prediction(
    alloy_system=["Cr", "Ta", "Ti", "W"],
    mol_ratio=[0.25, 0.25, 0.25, 0.25],
    temperature_min=300,
    temperature_max=3000,
    temperature_step=50,
    tdb_dir=TDB_DIR,
)

result.data.to_csv("phase_fractions.csv", index=False)
result.energy_above_hull_data.to_csv("bcc_energy_above_hull.csv", index=False)
result.figure.savefig("phase_fractions.png", dpi=300, bbox_inches="tight")
result.energy_above_hull_figure.savefig(
    "bcc_energy_above_hull.png", dpi=300, bbox_inches="tight"
)
print("Metastability threshold:", result.metastable_temperature)
print("Stable BCC threshold:", result.stable_temperature)
```

### Spinodal spectrum and soft mode

```python
from pathlib import Path

from alloy_web.config import ensure_project_imports

ensure_project_imports()

from alloy_web.adapters.spinodal_adapter import run_spinodal_analysis

interaction_file = Path(
    "external/Rapid_Phase_Field_Prediction/input/spinodal/"
    "binary_interactions.json"
)

result = run_spinodal_analysis(
    alloy_system=["Cr", "Ta", "Ti", "W"],
    mol_ratio=[0.25, 0.25, 0.25, 0.25],
    lattice="BCC",
    temperature_min=300,
    temperature_max=3000,
    temperature_step=25,
    mode_temperature=1500,
    interaction_data_path=interaction_file,
)

result.spectrum_data.to_csv("spinodal_spectrum.csv", index=False)
result.eigenvalue_figure.savefig("spinodal_spectrum.png", dpi=300)
result.mode_figure.savefig("spinodal_mode.png", dpi=300)
print("Estimated spinodal temperature:", result.spinodal_temperature)
print(result.interpretation)
```

Direct, lower-level functions are documented in the [calculation-engine guide](external/Rapid_Phase_Field_Prediction/README.md). Use those when you need finer control over grids or plotting; use adapters when you want the website's validation and result containers.

## Scientific definitions used by the interface

- **Miscible:** at least 99% of the equilibrium material is in one solid-solution phase: BCC_A2, FCC_A1, or HCP_A3. Two composition sets of the same phase, such as two distinct BCC_A2 solutions, count as multiphase rather than miscible.
- **Percentage miscible region (PMR):** the percentage of sampled compositions in a system that meet the miscibility definition at the selected temperature.
- **BCC energy above hull:** the homogeneous BCC_A2 Gibbs energy minus the equilibrium Gibbs-energy hull, reported in meV/atom. Zero indicates stability; the interface marks values up to 50 meV/atom as metastable.
- **Spinodal temperature:** the estimated temperature where the minimum constrained-composition Hessian eigenvalue crosses zero. The associated eigenvector describes the soft composition fluctuation mode.

These are operational definitions used by this codebase. Sampling density, temperature step, database coverage, and enabled phases affect the numerical result and should be reported with published calculations.

## Inputs, units, and data behavior

- Supply elements and mole fractions in the same order. Mole fractions must sum to one.
- Temperatures are in kelvin.
- BCC energy above hull is reported in meV/atom; thermodynamic interaction parameters retain the units defined by their source model.
- Thermodynamic databases live in `external/Rapid_Phase_Field_Prediction/input/tdb/`. They are calculation inputs and are treated as read-only by the current workflows.
- Many database filenames encode element order. Preserve the order used by an available filename when calling lower-level routines directly.
- The inter-system SQLite database is a generated calculation cache, not a scientific source of record. It may be rebuilt when inputs or calculation settings change.
- Experimental evidence is returned only when the stored record matches the requested alloy system under the adapter's matching rules. Citations remain attached to their source records.

## Testing

Run the web and adapter tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Run the Alloy Assistant tests separately:

```bash
python -m unittest discover -s alloy_assistant/tests -v
```

Some thermodynamic tests and examples are computationally expensive. A successful import or UI launch is not a substitute for checking numerical output against the database, composition, temperature grid, and phase selection used in a study.

## Citation

If you use the SymPlex visualization method, cite:

> J. Cavin, P. Omprakash, A. Couet, and R. Mishra, “SymPlex plots for visualizing properties in high-dimensional alloy spaces,” *Scripta Materialia* 268 (2025) 116840.

Other RAPTor components are associated with work in preparation. Until component-specific citations are published, cite the repository and record the commit or release used so the calculation can be reproduced.

## License

RAPTor is provided under the [MIT License](LICENSE). Thermodynamic databases and literature sources may have their own terms; users are responsible for complying with the terms of the data they supply or redistribute.
