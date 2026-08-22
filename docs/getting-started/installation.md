# Installation

RAPTor currently supports Python 3.11 and is installed from a repository
checkout. It is not yet published on PyPI.

```bash
git clone https://github.com/Materials-Modelling-Microscopy/RAPTor.git
cd RAPTor
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Verify the public package:

```bash
python -c "import raptor_alloys as rap; print(rap.__version__)"
```

Editable installation is convenient while RAPTor is changing: a later
`git pull` updates the code used by the environment. Use `pip install .` for a
fixed copy instead.

## Use RAPTor from another project

Activate the environment in which RAPTor was installed, then import it from
any working directory:

```python
import raptor_alloys as rap

print(rap.AVAILABLE_ELEMENTS)
print(rap.TDB_DIR)
```

The base installation contains the numerical stack used by the Python API.
The hosted application is available separately at
[raptor.engr.wustl.edu](https://raptor.engr.wustl.edu).

## Documentation environment

Contributors can install and preview these docs with:

```bash
python -m pip install -e ".[docs]"
mkdocs serve
```
