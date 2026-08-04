from pathlib import Path
from contextlib import contextmanager
import os
import sys

import numpy as np
import matplotlib.pyplot as plt


SYMPLEX_ROOT = Path(__file__).resolve().parent

if str(SYMPLEX_ROOT) not in sys.path:
    sys.path.insert(0, str(SYMPLEX_ROOT))

from main import main


@contextmanager
def working_directory(path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def interpolate_nans(arr):
    # trying to fix the symplex bug
    arr = np.asarray(arr, dtype=float)
    x = np.arange(len(arr))
    valid = ~np.isnan(arr)

    if valid.sum() == 0:
        return arr

    arr_interp = arr.copy()
    arr_interp[~valid] = np.interp(x[~valid], x[valid], arr[valid])
    return arr_interp


def _figure_score(fig):
    score = 0
    for ax in fig.axes:
        score += len(ax.patches)
        score += len(ax.collections)
        score += len(ax.lines)
        score += len(ax.texts)
        score += len(ax.images)
    return score


def _get_most_populated_figure(fallback_fig):
    """
    SymPlex sometimes draws into the current figure rather than the figure
    explicitly passed through plot_grid. This returns the figure with the
    most plotted artists.
    """
    figures = [fallback_fig]

    for num in plt.get_fignums():
        candidate = plt.figure(num)
        if candidate not in figures:
            figures.append(candidate)

    best_fig = max(figures, key=_figure_score)

    return best_fig


def generate_symplex_plot(
    alloy_system,
    temperature,
    constraint_element,
    property_name,
    data,
):
    plt.close("all")

    alloy_system = list(alloy_system)
    constraint_element_index = alloy_system.index(constraint_element)

    clean_data = {
        key: interpolate_nans(value)
        for key, value in data.items()
    }

    fig = plt.figure(figsize=(3.58, 4.5))
    ax1 = fig.add_subplot(projection="polar")

    ax1.set_yticks([])
    ax1.set_xticks([])
    ax1.spines["polar"].set_visible(False)
    ax1.grid(False)
    
    if property_name == "SPSS Phase Fraction":
        property_name = 'phase_fraction'
    elif property_name == "BCC Energy Above Hull":
        property_name = 'bcc_e_hull'
    elif property_name == "Number of Phases":
        property_name = 'no_of_phases'
    elif property_name == "Minimum Spinodal Eigenvalue":
        property_name = 'eigen_value'
    
    with working_directory(SYMPLEX_ROOT):
        out = main(
            composition=alloy_system,
            plot_grid=(fig, ax1),
            constraint_element_index=constraint_element_index,
            custom_data=clean_data,
            is_custom=True,
            property_str=property_name,
            cbar_hide=False,
            cbar_ax=ax1,
            central_point=None,
            special_points=None,
        )

    if out is not None:
        if isinstance(out, tuple):
            possible_fig = out[0]
            if hasattr(possible_fig, "savefig"):
                fig = possible_fig
        elif hasattr(out, "savefig"):
            fig = out

    fig = _get_most_populated_figure(fig)

    if len(fig.axes) > 0:
        ax = fig.axes[0]
        ax.text(
            0.95,
            -0.18,
            f"{temperature:.0f} K",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

    fig.canvas.draw()

    return fig
