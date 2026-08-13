# RAPTor

**Rapid Alloy Phase-field generaTOR** is research software for exploring phase stability in multi-principal-element and refractory alloy systems. It combines thermodynamic equilibrium calculations, spinodal analysis, high-dimensional SymPlex maps, phase-diagram plotting, system-level summaries, and experimental evidence in one source repository.

The Streamlit website is one way to use RAPTor. The numerical routines and validated adapter functions can also be run directly from Python for scripted studies, batch calculations, and downstream analysis. Access the website here: https://rapgen.streamlit.app

> **Research-code status:** the calculation engine and its adapters are installable as the `raptor_alloys` Python package from a checkout of this repository (not yet published to PyPI), but the interface is pre-1.0 and may still evolve. The Streamlit website is a separate, unaffected way to use the same code and continues to run from a plain `requirements.txt` install as before. Both come from this one repository, updated together.

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

## Quick start: Streamlit website

Python 3.11 is the supported runtime

```bash
git clone https://github.com/Pravanop/Phase_Field_Prediction_Visualization.git
cd Phase_Field_Prediction_Visualization

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

## Quick start: compute package (`raptor_alloys`)

If you just want to call calculations from your own scripts or notebooks — no Streamlit, no web browser — install the `raptor_alloys` package from the same checkout instead of `requirements.txt`. It pulls in only what the calculations themselves need (numpy, pandas, matplotlib, scipy, pycalphad, symengine, xarray, tinydb, pymatgen, pyyaml); Streamlit and the Alloy Assistant's dependencies are left out unless you ask for them.

```bash
git clone https://github.com/Pravanop/Phase_Field_Prediction_Visualization.git
cd Phase_Field_Prediction_Visualization

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

```python
import raptor_alloys as rap

result = rap.run_phase_diagram_prediction(
    alloy_system=["Cr", "W"],  # any element order is fine
    tdb_dir=rap.TDB_DIR,
)
result.figure.savefig("Cr-W.png", dpi=300, bbox_inches="tight")
```

This installs in editable mode, so the package always reflects your current checkout — pulling the repository picks up updates to both the compute package and the website together, since they're built from the same source. `pip install .` (without `-e`) instead builds a self-contained copy if you'd rather not track the checkout.

Two optional extras add back what the base install leaves out:

```bash
python -m pip install -e ".[web]"        # streamlit, to also run the website from this environment
python -m pip install -e ".[assistant]"  # duckdb, sentence-transformers, groq, for alloy_assistant
```

`raptor_alloys` is a thin, stable façade over the same calculation engine and adapters the website calls — see [Using the calculations without Streamlit](#using-the-calculations-without-streamlit) below for what it exposes.

## Repository guide

| Path | Role |
| --- | --- |
| [`raptor_alloys/`](raptor_alloys/) | Public, installable façade over the calculation engine and adapters below. The stable entry point for calling RAPTor from your own scripts. |
| [`external/Rapid_Phase_Field_Prediction/`](external/Rapid_Phase_Field_Prediction/) | Thermodynamic, phase-field, spinodal, and phase-diagram calculation engine. See its [calculation guide](external/Rapid_Phase_Field_Prediction/README.md). |
| [`external/Symplex/`](external/Symplex/) | High-dimensional simplex decomposition and plotting. See the [SymPlex guide](external/Symplex/README.md). |
| [`alloy_web/`](alloy_web/) | Validation and result adapters shared by the pages, plus UI components. See the [adapter guide](alloy_web/README.md). |
| [`pages/`](pages/) | Streamlit presentation layer. Scientific calculations should remain outside this directory. |
| [`alloy_assistant/`](alloy_assistant/) | Local DuckDB knowledge workspace, ingestion, reviewed queries, retrieval, and citation-preserving evidence. See the [assistant guide](alloy_assistant/README.md). |
| [`tests/`](tests/) | Tests for web adapters and cross-layer behavior. |

## Using the calculations without Streamlit

Install `raptor_alloys` as shown above, then import it directly — no `sys.path` setup required, and no Streamlit dependency pulled in. It re-exports the same adapter functions the website calls, so results are identical to what the corresponding page produces.

### Phase fractions and BCC energy above hull

```python
import raptor_alloys as rap

result = rap.run_phase_fraction_temperature_prediction(
    alloy_system=["Cr", "Ta", "Ti", "W"],
    mol_ratio=[0.25, 0.25, 0.25, 0.25],
    temperature_min=300,
    temperature_max=3000,
    temperature_step=50,
    tdb_dir=rap.TDB_DIR,
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

import raptor_alloys as rap

interaction_file = Path(
    "external/Rapid_Phase_Field_Prediction/input/spinodal/"
    "binary_interactions.json"
)

result = rap.run_spinodal_analysis(
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

The remaining six calculations (`run_phase_diagram_prediction`, `run_composition_splitting_prediction`, `run_symplex_prediction`, `run_pathway_analysis`, `run_alloy_system_summary`, `run_inter_system_comparison`) follow the same pattern — call `rap.<name>(...)`; run `help(rap)` or check [`raptor_alloys/__init__.py`](raptor_alloys/__init__.py) for the full list and each function's result type.

If you're working from a checkout without installing (e.g. editing the adapters themselves), the same functions are reachable directly as `alloy_web.adapters.<module>.run_...` after calling `alloy_web.config.ensure_project_imports()` — that's what `raptor_alloys` does internally. Direct, lower-level engine functions below the adapter layer are documented in the [calculation-engine guide](external/Rapid_Phase_Field_Prediction/README.md); use those when you need finer control over grids or plotting than an adapter exposes.

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
