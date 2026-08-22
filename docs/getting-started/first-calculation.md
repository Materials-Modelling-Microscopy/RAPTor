# First calculation

This binary phase diagram is the smallest complete example of the public API.

```python
import matplotlib.pyplot as plt
import raptor_alloys as rap

result = rap.run_phase_diagram_prediction(
    alloy_system=["Cr", "W"],
    tdb_dir=rap.TDB_DIR,
    temperature_min=300,
    temperature_max=3000,
    temperature_step=25,
    composition_step=0.02,
)

print(result.composition)
print(result.diagram_type)
result.figure.savefig("Cr-W-phase-diagram.png", dpi=300, bbox_inches="tight")
plt.close(result.figure)
```

RAPTor resolves databases by element set. If the database filename uses a
different element order, `result.alloy_system` and `result.composition` report
the resolved order.

!!! note "Calculation cost"
    CALPHAD calculations are substantially slower than importing the package.
    Begin with coarse temperature and composition steps, then refine the grid
    after checking that the system and phase selection are appropriate.

## Common failures

- `FileNotFoundError` means no TDB in `tdb_dir` covers the requested set.
- `ValueError` usually indicates an unsupported system order, missing ternary
  temperature, or inconsistent composition.
- A numerically completed calculation is not automatically scientifically
  appropriate; inspect database coverage and enabled phases.
