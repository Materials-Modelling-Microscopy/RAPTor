<p align="center">
  <img src="alloy_web/assets/icons/raptor-github-logo.png#gh-light-mode-only" alt="RAPTor logo" width="240">
  <img src="alloy_web/assets/icons/raptor-github-logo-dark.png#gh-dark-mode-only" alt="RAPTor logo" width="240">
</p>

<h1 align="center">RAPTor</h1>

<p align="center">
  <strong>Rapid Alloy Phase-field generaTOR</strong><br>
  Research software for computational alloy thermodynamics and phase-stability analysis
</p>

<p align="center">
  <a href="https://github.com/Materials-Modelling-Microscopy/RAPTor/actions/workflows/docs.yml"><img src="https://github.com/Materials-Modelling-Microscopy/RAPTor/actions/workflows/docs.yml/badge.svg" alt="Documentation workflow"></a>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/status-research%20software-6f42c1" alt="Research software status">
  <a href="https://raptor.engr.wustl.edu"><img src="https://img.shields.io/badge/launch-hosted%20application-2ea44f" alt="Launch the hosted RAPTor application"></a>
  <a href="https://doi.org/10.48550/arXiv.2609.06627"><img src="https://img.shields.io/badge/DOI-10.48550%2FarXiv.2609.06627-blue" alt="RAPTor paper DOI"></a>
</p>

<p align="center">
  <a href="https://raptor.engr.wustl.edu"><strong>Launch RAPTor</strong></a>
  ·
  <a href="docs/index.md">Documentation</a>
  ·
  <a href="docs/getting-started/installation.md">Installation</a>
  ·
  <a href="#citation">Citation</a>
</p>

---

## Funding and acknowledgements

RAPTor is developed through a collaboration between researchers at Washington
University in St. Louis and the University of Wisconsin–Madison. Development
of this project has been partially supported by Schmidt Futures.

<table>
  <tr>
    <td align="center" width="50%">
      <img src="alloy_web/assets/partners/washu-logo.jpg" alt="Washington University in St. Louis" width="360">
    </td>
    <td align="center" width="50%">
      <img src="alloy_web/assets/partners/uw-logo-horizontal-color-web-digital.svg" alt="University of Wisconsin–Madison" width="360">
    </td>
  </tr>
</table>

<p align="center"><em>Partially supported by</em></p>

<p align="center">
  <img src="alloy_web/assets/partners/schmidt-futures-logo.png" alt="Schmidt Futures" width="315">
</p>

## Overview

RAPTor is an open-source research platform for exploring phase stability in
multi-principal-element and refractory alloy systems. It brings together
thermodynamic equilibrium calculations, spinodal analysis, high-dimensional
SymPlex maps, phase-diagram construction, system-level comparisons, and
experimental evidence within a unified Python and web interface.

The project can be used in two ways:

- **Interactive application:** run calculations and inspect results through the
  hosted interface at [raptor.engr.wustl.edu](https://raptor.engr.wustl.edu).
- **Python API:** call the numerical routines directly in scripts, notebooks,
  batch studies, and downstream analysis pipelines.

> [!IMPORTANT]
> RAPTor is pre-1.0 research software. Its interfaces and scientific models may
> continue to evolve. Results should be interpreted in the context of the
> selected thermodynamic database, modeled phases, numerical settings, and
> sampling resolution.

## Scientific capabilities

| Capability | Representative outputs |
| --- | --- |
| **SymPlex property maps** | SPSS phase fraction, BCC energy above hull, phase count, and minimum spinodal eigenvalue across high-dimensional composition spaces |
| **Temperature-dependent phase stability** | Equilibrium phase fractions and BCC energy above hull for a selected alloy composition |
| **Composition splitting** | Equilibrium phase compositions and elemental partitioning at selected temperatures |
| **Phase diagrams** | Binary temperature–composition diagrams and isothermal ternary diagrams |
| **Spinodal analysis** | Constrained-composition Hessian spectra, spinodal crossing temperatures, and soft composition modes |
| **Alloy-system summaries** | Miscibility temperature, percentage miscible region, subsystem behavior, and considered intermetallic phases |
| **Inter-system comparison** | Ranking and Pareto filtering across multiple alloy systems and stability metrics |
| **Experimental evidence** | Provenance-preserving records and reviewed literature evidence associated with alloy systems |

The current thermodynamic workflows focus on the `BCC_A2`, `FCC_A1`, and
`HCP_A3` solid-solution phases represented in the supplied thermodynamic
databases, together with applicable intermetallic phases.

## Quick start

Python 3.11 is the supported runtime. Clone the repository and install RAPTor
in a virtual environment:

```bash
git clone https://github.com/Materials-Modelling-Microscopy/RAPTor.git
cd RAPTor

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

The editable installation keeps the Python package synchronized with the local
checkout. Use `python -m pip install .` instead when a self-contained installed
copy is preferred.

### Minimal example

```python
import raptor_alloys as rap

result = rap.run_phase_diagram_prediction(
    alloy_system=["Cr", "W"],
    tdb_dir=rap.TDB_DIR,
)

result.figure.savefig("Cr-W.png", dpi=300, bbox_inches="tight")
```

For additional examples, see the guides for
[phase stability](docs/guides/phase-stability.md),
[phase diagrams](docs/guides/phase-diagrams.md),
[spinodal analysis](docs/guides/spinodal.md),
[SymPlex maps](docs/guides/symplex.md), and
[system screening](docs/guides/system-screening.md).

## Repository structure

| Path | Purpose |
| --- | --- |
| [`raptor_alloys/`](raptor_alloys/) | Public, result-oriented Python API |
| [`alloy_web/`](alloy_web/) | Validated calculation adapters and Streamlit application components |
| [`alloy_assistant/`](alloy_assistant/) | Local evidence workspace, ingestion, retrieval, and citation-preserving records |
| [`external/Rapid_Phase_Field_Prediction/`](external/Rapid_Phase_Field_Prediction/) | Foundational thermodynamic, phase-field, spinodal, and phase-diagram routines |
| [`external/Symplex/`](external/Symplex/) | High-dimensional simplex decomposition and visualization routines |
| [`docs/`](docs/) | Concepts, calculation guides, API references, and development documentation |
| [`tests/`](tests/) | Web-adapter, API, documentation, and cross-layer tests |

## Scientific definitions and interpretation

- **Miscible:** at least 99% of the equilibrium material is present in one
  solid-solution phase: `BCC_A2`, `FCC_A1`, or `HCP_A3`. Two composition sets
  of the same phase count as a multiphase state rather than a miscible state.
- **Percentage miscible region (PMR):** the percentage of sampled compositions
  in a system that meet the miscibility definition at the selected temperature.
- **BCC energy above hull:** the homogeneous `BCC_A2` Gibbs energy minus the
  equilibrium Gibbs-energy hull, reported in meV/atom. Zero indicates
  thermodynamic stability; the interface identifies values up to 50 meV/atom
  as metastable.
- **Spinodal temperature:** the estimated temperature at which the minimum
  constrained-composition Hessian eigenvalue crosses zero. The associated
  eigenvector describes the soft composition-fluctuation mode.

Temperatures are reported in kelvin. Thermodynamic interaction parameters
retain the units defined by their source model. Database coverage, phase-model
selection, temperature increments, and composition sampling density all affect
the numerical results and should be reported in scientific use.

## Documentation and testing

The repository documentation begins at [`docs/index.md`](docs/index.md). Public
functions and result types are listed in the
[API reference](docs/reference/api.md), while calculation-specific workflows
are described in the [user guides](docs/guides/index.md).

Run the primary test suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

Run the evidence-workspace tests separately:

```bash
python -m unittest discover -s alloy_assistant/tests -v
```

Some thermodynamic tests and examples are computationally expensive. A
successful import or application launch is not a substitute for validating
scientific output against the database, composition, temperature grid, and
phase selection used in a study.

## Citation

If RAPTor is used in research, please cite the primary publication:

> P. Omprakash, N. Crnkovich, J. Cavin, N. Curtis, A. Couet, and R. Mishra,
> “First-principles-based Prediction of Phase Fields: Part I. Binary and
> Ternary Refractory Alloys,” *arXiv:2609.06627* (`cond-mat.mtrl-sci`, 2026).
> <https://doi.org/10.48550/arXiv.2609.06627>

For reproducibility, also record the RAPTor release or commit hash,
thermodynamic database, modeled phases, and calculation settings used to
produce the reported results.

### Method-specific citation

For use of the SymPlex visualization method, please cite:

> J. Cavin, P. Omprakash, A. Couet, and R. Mishra, “SymPlex plots for
> visualizing properties in high-dimensional alloy spaces,” *Scripta
> Materialia* **268** (2025), 116840.

Other RAPTor components are associated with work in preparation. Additional
component-specific references are provided in the application and
documentation where applicable.

## Contributing

Bug reports, scientific validation cases, documentation improvements, and
well-scoped code contributions are welcome through GitHub Issues and pull
requests. Please describe the thermodynamic database, modeled phases,
composition, temperature range, and expected behavior when reporting a
scientific discrepancy.

## License

RAPTor is distributed under the [MIT License](LICENSE). Thermodynamic databases
and literature sources may be governed by separate terms; users are responsible
for complying with the licenses and redistribution requirements of the data
they supply or reuse.
