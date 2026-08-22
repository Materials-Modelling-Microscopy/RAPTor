# RAPTor Python API

RAPTor provides CALPHAD-based phase-stability calculations for
multi-principal-element and refractory alloys. This site documents the
installable `raptor_alloys` Python API for scripts, notebooks, batch studies,
and downstream applications.

```python
import raptor_alloys as rap

result = rap.run_phase_diagram_prediction(
    alloy_system=["Cr", "W"],
    tdb_dir=rap.TDB_DIR,
)
result.figure.savefig("Cr-W.png", dpi=300, bbox_inches="tight")
```

## Compute layers

`raptor_alloys` provides a compact import surface for common calculations and
named result objects. The foundational scientific functions live under
`external/Rapid_Phase_Field_Prediction` and `external/Symplex`; they are the
base compute implementations and are available directly when a project needs
lower-level control. The adapters add input validation and collect tables,
figures, and metadata into convenient result objects.

RAPTor is pre-1.0 research software. Record the package version, repository
commit, thermodynamic database, interaction data, and calculation settings for
any result that must be reproduced.

## Where to begin

- [Install RAPTor](getting-started/installation.md) in a fresh environment.
- Run the [first calculation](getting-started/first-calculation.md).
- Learn how to [inspect and save result objects](getting-started/working-with-results.md).
- Choose a workflow from the [calculation guide](guides/index.md).

The hosted application is available at
[raptor.engr.wustl.edu](https://raptor.engr.wustl.edu). Website operation and
maintenance are intentionally outside the scope of these docs.
