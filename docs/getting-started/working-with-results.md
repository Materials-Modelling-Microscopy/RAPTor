# Working with results

Every calculation returns a named dataclass rather than an unstructured tuple.
Fields commonly include pandas tables, Matplotlib figures, normalized inputs,
scientific summary values, and calculation-cost metadata.

```python
result = rap.run_phase_fraction_temperature_prediction(...)

result.data.to_csv("phase-fractions.csv", index=False)
result.energy_above_hull_data.to_csv("energy-above-hull.csv", index=False)
result.figure.savefig("phase-fractions.png", dpi=300, bbox_inches="tight")
```

Several result types provide serialization helpers such as `to_csv_bytes()`,
`to_png_bytes()`, or `to_pickle_bytes()`. These are useful for web responses or
object storage; scripts can normally call pandas and Matplotlib directly.

## Inspect before assuming a schema

Research tables may gain columns as calculations evolve. Inspect fields and
column names explicitly:

```python
from dataclasses import fields

print([field.name for field in fields(result)])
print(result.data.columns.tolist())
print(result.data.head())
```

The [result-object reference](../reference/results.md) documents stable field
meanings. Save the raw tables alongside any derived plots or statistics.
