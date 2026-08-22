# Scientific definitions and units

## Operational definitions

**Miscible** means at least the configured threshold—99% by default—of the
equilibrium material is in one solid-solution composition set: BCC_A2, FCC_A1,
or HCP_A3. Two distinct composition sets of the same phase count as multiphase.

**Percentage miscible region (PMR)** is the percentage of sampled compositions
that meet the miscibility definition at a selected temperature.

**BCC energy above hull** is homogeneous BCC_A2 Gibbs energy minus the
equilibrium Gibbs-energy hull. Zero indicates stability. RAPTor currently uses
50 meV/atom as an operational metastability threshold.

**Spinodal temperature** is the estimated temperature at which the minimum
constrained-composition Hessian eigenvalue crosses zero.

## Units

- Temperatures: kelvin.
- Composition: mole fraction unless explicitly labelled otherwise.
- Energy above hull and integrated pathway burden: meV/atom.
- Thermodynamic interaction parameters: their source-model units; TDB summary
  tables label J/mol and converted eV/atom columns explicitly.
- Pressure in equilibrium calculations: 101325 Pa unless stated otherwise.

Sampling density, temperature spacing, database coverage, enabled phases, and
thresholds are part of the scientific definition of a computed result.
