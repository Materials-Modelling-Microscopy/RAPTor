# Comparison metrics

`run_inter_system_comparison` accepts the following exact identifiers.

| Identifier | Unit | Pareto direction |
| --- | --- | --- |
| `miscibility_temperature` | K | Lower |
| `spinodal_temperature` | K | Context-dependent; excluded |
| `pmr` | % | Higher |
| `equimolar_solid_solution_fraction` | % | Higher |
| `active_phase_count` | count | Lower |
| `metastability_gap` | K | Lower |
| `mean_path_burden` | meV/atom | Context-dependent |
| `path_burden_variance` | (meV/atom)² | Context-dependent |

Context-dependent metrics are reported but do not receive a universal
optimization direction. Their preferred direction depends on the design goal.
