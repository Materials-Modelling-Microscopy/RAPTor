## Symplex Plots

Method to decompose high dimensional simplices into high symmetry paths for visualizing Multi Principal Element Alloys (MPEAs).

Within RAPTor, SymPlex is the visualization layer for quaternary and quinary
property grids calculated by `external/Rapid_Phase_Field_Prediction`. The web
adapter in `alloy_web/adapters/symplex_adapter.py` joins the data generator and
the plotter, so a separate SymPlex clone is not required when using this
repository. See the root [README](../../README.md) for an end-to-end example.

Cite this work at https://arxiv.org/pdf/2504.03973

![Polar plot for Gibbs Free Energy for _ABCD_](./plots/A-B-C-D_None_gibbs.png)

To use SymPlex as a standalone project:

```bash
git clone https://github.com/Materials-Modelling-Microscopy/Symplex.git
```

Install the requirements in a virtualenv:
```bash
cd Symplex
pip install -r requirements.txt
```
An example notebook, example.ipynb has been provided with detailed instructions on how to plot pre-loaded properties and custom user data.
