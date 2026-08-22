# Documentation standard

Public docstrings use Google style and answer four questions: what is computed,
what every input means and its unit, what is returned, and what can fail.

Every public function must include `Args`, `Returns`, and `Raises`. Scientific
assumptions or performance warnings belong in `Notes`. Result dataclasses must
state field units and the meaning of sentinel values such as `None`.

Guides are task-oriented and contain runnable examples. Use `raptor_alloys` for
the compact, result-oriented interface. Link to the foundational functions in
`external/Rapid_Phase_Field_Prediction` or `external/Symplex` when lower-level
control is relevant. Reference pages are generated from source docstrings to
avoid duplicating signatures manually.

Documentation changes are required when a public signature, return field,
accepted identifier, scientific definition, default, database, or numerical
interpretation changes.

Calculation guides show representative outputs as well as code. Refresh the
versioned figures and tables with `python scripts/generate_docs_outputs.py`
whenever calculation or plotting behavior changes.
