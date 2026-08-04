from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from pycalphad import calculate, Database


J_PER_MOL_PER_MEV_ATOM = 96.485
STABLE_TOLERANCE_MEV_ATOM = 1e-6
METASTABLE_LIMIT_MEV_ATOM = 50.0


def calculate_homogeneous_bcc_gibbs(
    database: Database,
    components: list[str],
    mols: list[list[float]] | np.ndarray,
    temperatures: list[float] | np.ndarray,
) -> np.ndarray:
    """Return homogeneous BCC_A2 Gibbs energies with shape (temperature, composition)."""
    if "BCC_A2" not in database.phases:
        raise ValueError("BCC_A2 is not available in this thermodynamic database.")

    components = [str(component).upper() for component in components]
    mols = np.atleast_2d(np.asarray(mols, dtype=float))
    temperatures = np.atleast_1d(np.asarray(temperatures, dtype=float))
    if mols.shape[1] != len(components):
        raise ValueError("Each composition must contain one mole fraction per component.")

    component_index = {component: index for index, component in enumerate(components)}
    constituents = sorted(database.phases["BCC_A2"].constituents[0])
    constituent_names = [str(species).upper() for species in constituents]
    missing = [name for name in constituent_names if name not in component_index]
    if missing or len(constituent_names) != len(components):
        raise ValueError(
            "BCC_A2 constituents do not match the selected components: "
            f"{constituent_names} versus {components}."
        )

    points = mols[:, [component_index[name] for name in constituent_names]]
    result = calculate(
        database,
        components + ["VA"],
        ["BCC_A2"],
        output="GM",
        T=temperatures,
        P=101325.0,
        points=points,
    )
    return np.asarray(result.GM, dtype=float).reshape(len(temperatures), len(points))


def energy_above_hull_mev(
    bcc_gibbs_j_per_mol: np.ndarray,
    equilibrium_gibbs_j_per_mol: np.ndarray,
) -> np.ndarray:
    """Convert BCC minus equilibrium Gibbs energy to non-negative meV/atom."""
    difference = (
        np.asarray(bcc_gibbs_j_per_mol, dtype=float)
        - np.asarray(equilibrium_gibbs_j_per_mol, dtype=float)
    ) / J_PER_MOL_PER_MEV_ATOM
    return np.maximum(difference, 0.0)


def first_temperature_at_or_below(
    temperatures: np.ndarray,
    energies: np.ndarray,
    threshold: float,
) -> float | None:
    """Find the first downward threshold crossing, with linear interpolation."""
    temperatures = np.asarray(temperatures, dtype=float)
    energies = np.asarray(energies, dtype=float)
    finite = np.isfinite(temperatures) & np.isfinite(energies)
    temperatures = temperatures[finite]
    energies = energies[finite]
    if len(temperatures) == 0:
        return None
    if energies[0] <= threshold:
        return float(temperatures[0])

    for index in range(1, len(temperatures)):
        previous_energy = energies[index - 1]
        energy = energies[index]
        if previous_energy > threshold >= energy:
            if np.isclose(previous_energy, energy):
                return float(temperatures[index])
            fraction = (previous_energy - threshold) / (previous_energy - energy)
            return float(
                temperatures[index - 1]
                + fraction * (temperatures[index] - temperatures[index - 1])
            )
    return None


def plot_bcc_energy_above_hull(
    temperatures: np.ndarray,
    energies: np.ndarray,
):
    temperatures = np.asarray(temperatures, dtype=float)
    energies = np.asarray(energies, dtype=float)
    finite = np.isfinite(temperatures) & np.isfinite(energies)
    temperatures = temperatures[finite]
    energies = energies[finite]
    if len(temperatures) == 0:
        raise ValueError("No finite BCC energy-above-hull results are available to plot.")

    threshold_temperature = first_temperature_at_or_below(
        temperatures, energies, METASTABLE_LIMIT_MEV_ATOM
    )
    stable_temperature = first_temperature_at_or_below(
        temperatures, energies, STABLE_TOLERANCE_MEV_ATOM
    )

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    upper_limit = max(60.0, float(np.nanmax(energies)) * 1.12)
    # metastable = (
    #     (energies > STABLE_TOLERANCE_MEV_ATOM)
    #     & (energies <= METASTABLE_LIMIT_MEV_ATOM)
    # )
    # stable = energies <= STABLE_TOLERANCE_MEV_ATOM
    axis.plot(
        temperatures, energies, color="gold", linewidth=2.3,
        marker="o", markersize=10, label="BCC_A2", markeredgecolor = 'k'
    )
    axis.axhline(
        METASTABLE_LIMIT_MEV_ATOM, color="#bd6b13", linestyle="--", linewidth=1.3,
        label="50 meV/atom",
    )
    if threshold_temperature is not None:
        axis.axvline(
            threshold_temperature, color="#bd6b13", linestyle=":", linewidth=1.4,
            label=f"50 meV at {threshold_temperature:.0f} K",
        )
    if stable_temperature is not None:
        axis.axvline(
            stable_temperature, color="#167452", linestyle=":", linewidth=1.5,
            label=f"0 meV at {stable_temperature:.0f} K",
        )

    axis.set_xlim(float(temperatures.min()), float(temperatures.max()))
    axis.set_ylim(0.0, upper_limit)
    axis.set_xlabel("Temperature (K)")
    axis.set_ylabel("BCC_A2 energy above hull (meV/atom)")
    axis.set_title("BCC solid-solution stability", loc="left", fontweight="bold")
    axis.grid(False)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8, ncol=2)
    figure.tight_layout()
    return figure, threshold_temperature, stable_temperature
