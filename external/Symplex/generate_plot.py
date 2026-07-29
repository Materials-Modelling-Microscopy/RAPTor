from typing import List, Iterable

from main import main
import numpy as np
import pickle
import matplotlib.pyplot as plt


def interpolate_nans(arr):
    arr = np.asarray(arr, dtype=float)

    x = np.arange(len(arr))
    valid = ~np.isnan(arr)

    # If all values are nan, interpolation is impossible
    if valid.sum() == 0:
        return arr

    arr_interp = arr.copy()
    arr_interp[~valid] = np.interp(x[~valid], x[valid], arr[valid])

    return arr_interp


def generate_symplex_plot(alloy_system, temperature, constraint_element, property_name, data):
    
    constraint_element_index = alloy_system.index(constraint_element)
    
<<<<<<< Updated upstream
    fig = plt.figure(figsize=(6, 6))
=======
    fig = plt.figure(figsize=(5, 5))
>>>>>>> Stashed changes
    ax1 = fig.add_subplot(projection='polar')
    ax1.set_yticks([])
    ax1.set_xticks([])
    ax1.spines["polar"].set_visible(False)
    ax1.grid(False)
    
    if property_name == 'SPSS Phase Fraction':
        property_str = 'phase_fraction'
    elif property_name == 'Number of Phases':
        property_str = 'no_of_phases'
    elif property_name == 'Minimum Spinodal Eigenvalue':
        property_str = 'eigen_value'
    
    custom_data = {
    key: interpolate_nans(value)
    for key, value in data.items()}
    
    is_custom = True
    
    plot_grid = fig, ax1
    central_point = None
    special_points = None
    
    _ = main(composition=alloy_system,
                    plot_grid=plot_grid,
                    constraint_element_index=constraint_element_index,
                    custom_data=custom_data,
                    is_custom=is_custom,
                    property_str=property_str,
                    cbar_hide=False,
                    cbar_ax=ax1,
                    central_point=central_point,
                    special_points=special_points)
    
<<<<<<< Updated upstream
    # ax1.text(0.95, -0.18, f"{temperature}K", ha='center', va='center', transform=ax1.transAxes)
    # fig.tight_layout()
=======
    ax1.text(0.95, -0.18, f"{temperature}K", ha='center', va='center', transform=ax1.transAxes)
    fig.tight_layout(pad = 0.0)
>>>>>>> Stashed changes
    return fig

    
