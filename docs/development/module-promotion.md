# Promote a research module into the API

Research workspaces such as eutectics, higher-order intermetallics, phase-field
experiments, and future Monte Carlo implementations do not become documented
API modules merely because their code exists in the repository.

A module is ready for public API promotion when it has:

1. A small typed Python entry point independent of presentation and
   command-line parsing.
2. Validated inputs and explicit, documented exceptions.
3. Named result dataclasses with units and stable field meanings.
4. No implicit writes; output paths and caches are explicit.
5. Deterministic controls where applicable, including random seeds.
6. Unit tests plus at least one scientifically checked reference case.
7. Packaged input data with provenance and licensing recorded.
8. A user guide, API reference, limitations, and reproducible example.
9. An entry in `raptor_alloys` and its `__all__` declaration.
10. A changelog entry describing scientific and API consequences.

## Required documentation packet

Each promoted module receives an overview, scientific model/equations, inputs
and units, output schema, minimal example, limitations/validity domain,
performance notes, reproducibility requirements, and citation/data provenance.

Monte Carlo modules must additionally document the random-number generator,
seed, initialization, equilibration/burn-in, sampling interval, convergence
diagnostics, replica or chain behavior, and uncertainty calculation.
