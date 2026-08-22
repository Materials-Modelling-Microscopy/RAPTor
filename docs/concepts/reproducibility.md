# Reproducibility

For every saved or published result, record:

- `raptor_alloys.__version__` and the repository commit hash;
- requested and resolved element order;
- mole fractions and units;
- all temperature and composition grid settings;
- TDB filename and file hash;
- interaction-data filename and file hash, when used;
- included phases and thresholds;
- cache state only as performance metadata, never as scientific provenance;
- returned calculation counts and elapsed time where available.

Generated SQLite caches are accelerators, not sources of record. Raw result
tables, source inputs, and settings should be retained independently.

Numerical convergence should be checked by repeating important calculations on
a finer grid. A successful calculation establishes software execution, not
agreement with experiment or suitability of the database for the alloy system.
