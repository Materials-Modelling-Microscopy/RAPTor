# Processing pathways

Processing-path analysis compares every unique sequential route from a starting
binary to a target ternary, quaternary, or quinary composition.

```python
import raptor_alloys as rap

result = rap.run_pathway_analysis(
    alloy_system=["Cr", "Mo", "Nb"],
    mol_ratio=[1 / 3, 1 / 3, 1 / 3],
    temperature=1500,
    tdb_dir=rap.TDB_DIR,
    points_per_segment=3,
)

print(result.starting_binaries)
print(result.mean_integrated_burden)
print(result.path_dependence_variance)
```

## Representative output

| Starting binary | Path | Integrated burden (meV/atom) |
| --- | --- | ---: |
| Mo-Nb | Mo-Nb → Cr-Mo-Nb | 22.44 |
| Cr-Mo | Cr-Mo → Cr-Mo-Nb | 29.44 |
| Cr-Nb | Cr-Nb → Cr-Mo-Nb | 60.99 |

For this coarse three-point-per-segment example, the mean integrated burden is
**37.62 meV/atom** and the path-dependence variance is
**281.07 (meV/atom)²**. The largest burden belongs to the Cr-Nb starting route.
The complete result rows are in [pathways.csv](../assets/outputs/pathways.csv)
and [pathway-points.csv](../assets/outputs/pathway-points.csv).

The integrated burden is based on BCC_A2 energy above the equilibrium hull.
Path resolution affects the numerical integral, so report
`points_per_segment` with results.
