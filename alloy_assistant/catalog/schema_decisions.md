# Schema Decisions

Version: 0.2  
Status: reviewed scientific definitions; database not yet created

## Governing units

- Temperature: kelvin (`K`)
- Composition: atomic fraction
- Pair mixing enthalpy: electronvolts per atom (`eV/atom`)
- Percentage miscible region (PMR): percent (`0` to `100`)

Units remain explicit in table and column definitions. Source values are not
silently converted or overwritten.

## Scientific definitions

### Alloy system and composition

An alloy system is an unordered set of elements. A composition assigns an
atomic fraction to each element in the system. Equimolar and non-equimolar
compositions therefore share a system but have different composition records.

### Percentage miscible region

PMR is the percentage of the sampled composition grid that is miscible at a
specified temperature. The current grid advances each elemental atomic
fraction in increments of `0.1`.

PMR is stored as a percentage in the curated database because that is the
domain definition used by the source files. A check constraint limits it to
`0 <= PMR <= 100`.

### Pair mixing enthalpy

Pair mixing enthalpy is calculated at `0 K` using DFT and is expressed in
`eV/atom`. One record is stored per canonical element pair. Positional source
columns such as `HmixAB` are decoded into explicit element pairs.

The multicomponent `Hmix` column in the current equimolar exports is treated as
a legacy derived metric rather than a primary fact. It can be reconstructed
from reviewed pair values once its exact aggregation rule is confirmed.

### Miscibility temperature

All temperatures are expressed in kelvin. A reported source value of
`T_misc = 0 K` means stable at room temperature and is normalized to `300 K`.

Both values are retained:

- `reported_miscibility_temperature_K`: exact source value;
- `miscibility_temperature_K`: scientifically normalized value;
- `normalization_rule`: `none` or `zero_to_room_temperature`.

This preserves auditability while making scientific queries behave correctly.
Other positive predictions below room temperature remain unchanged; for
example, a reported `200 K` remains `200 K`.

### Melting temperature

The alloy melting temperature used here is the composition-weighted arithmetic
mean of the elemental melting temperatures:

```text
T_melt(alloy) = sum(x_i * T_melt(element_i))
```

Elemental melting temperatures require their own source provenance. The
weighted value will be calculated in a SQL view and compared against the
legacy CSV value during validation.

### Experimental validation

`refractory_hea_validation.csv` is currently treated as the authoritative
curated source because it was manually reviewed by the author. Publication
mapping exists but is deferred. Records will carry a
`provenance_status = 'publication_mapping_pending'` flag until that mapping is
added.

### Legacy `condition`

`condition` probably represents the number of phases, but it is excluded from
the curated MVP because its definition is not required and has not been
verified. It remains untouched in the raw source files.

## Data-quality decisions

- Exported dataframe indexes such as `Unnamed: 0` are discarded during
  curation.
- Original composition strings and phase labels are retained alongside
  normalized representations.
- Duplicate experimental rows are flagged for review rather than automatically
  deleted.
- Phase dictionaries stored as text are converted to one phase-fraction row per
  phase, temperature, composition, and calculation run.
- Missing publication mappings remain visibly incomplete; they are not
  fabricated.
- TDB files are initially registered as versioned calculation inputs rather
  than decomposed into thousands of parameter rows.

## Database layers

1. **Raw files**: immutable source artifacts.
2. **Staging tables**: faithful imports with source row numbers.
3. **Curated tables**: normalized scientific entities and facts.
4. **Views**: derived values such as weighted melting temperature and
   miscibility ratio.
5. **Generated indexes**: document embeddings and vector indexes that can be
   rebuilt from curated text.

## DuckDB namespace decision

All relational tables live in one SQL schema named `alloy`. DuckDB does not
support foreign keys across SQL schemas, so separating tables into `catalog`,
`core`, `science`, and `literature` namespaces would prevent referential
integrity. Those concepts remain as documented sections and will also be
reflected in the Python module structure.
