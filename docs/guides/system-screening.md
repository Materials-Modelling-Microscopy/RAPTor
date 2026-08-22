# System summaries and comparison

Use `run_alloy_system_summary` to inspect one complete system and all available
subsystems. It combines miscibility searches, percentage miscible region,
intermetallic phases, and interaction tables.

```python
import raptor_alloys as rap

interactions = rap.TDB_DIR.parent / "spinodal" / "binary_interactions.json"

system = rap.run_alloy_system_summary(
    alloy_system=["Cr", "W"],
    reference_temperature=1500,
    temperature_min=300,
    temperature_max=2400,
    temperature_step=300,
    tdb_dir=rap.TDB_DIR,
    interaction_data_path=interactions,
    max_sample_points=30,
)
```

## Representative summary output

| System | Miscibility transition | Miscible at 1500 K | Active phases |
| --- | --- | --- | --- |
| Cr-W | Not found through 2400 K | No | BCC_A2, BCC_A2 |

The duplicate BCC_A2 entries are distinct equilibrium composition sets. Five
of the 30 sampled compositions are classified as miscible, giving a coarse PMR
of **16.7%**. See [system-summary.csv](../assets/outputs/system-summary.csv) and
[system-phase-breakdown.csv](../assets/outputs/system-phase-breakdown.csv).

Use `run_inter_system_comparison` to generate same-order systems from an element
pool, compute selected metrics, rank them, and identify Pareto candidates.

```python
comparison = rap.run_inter_system_comparison(
    element_pool=["Cr", "Mo", "W"],
    order=2,
    selected_metrics=["active_phase_count"],
    primary_metric="active_phase_count",
    reference_temperature=1500,
    temperature_min=300,
    temperature_max=2400,
    temperature_step=300,
    lattice="BCC",
    tdb_dir=rap.TDB_DIR,
    interaction_data_path=interactions,
    cache_path="raptor-comparison.sqlite",
)
```

## Representative comparison output

| Rank | System | Active phase count | Pareto optimal |
| ---: | --- | ---: | --- |
| 1 | Mo-W | 1 | Yes |
| 2 | Cr-Mo | 2 | No |
| 2 | Cr-W | 2 | No |

All three candidates completed. With active phase count as the only objective,
Mo-W is the sole Pareto candidate. The exact generated table is available as
[system-comparison.csv](../assets/outputs/system-comparison.csv).

Comparison is intentionally failure-tolerant: one unavailable or failed metric
does not discard all other candidates. Inspect status/display columns and
`complete_count` before using the ranking. Reuse the SQLite cache for identical
inputs; its keys include settings and source signatures.
