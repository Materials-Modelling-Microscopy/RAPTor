from pathlib import Path
import io

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from phase_diagram_generators.spinodal_predictor import (
    load_interaction_data,
    spinodal_spectrum,
)


def compute_spinodal_vs_temperature(
    composition: list[str],
    mol_ratio: list[float],
    lattice: str,
    interaction_data: dict,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
) -> pd.DataFrame:
    """
    Compute spinodal eigenvalue spectrum across a temperature grid.
    """

    temperatures = np.arange(
        float(temperature_min),
        float(temperature_max) + 0.5 * float(temperature_step),
        float(temperature_step),
    )

    rows = []

    for T in temperatures:
        result = spinodal_spectrum(
            composition=composition,
            temperature=float(T),
            lattice=lattice,
            mol=mol_ratio,
            interaction_data=interaction_data,
        )

        row = {
            "temperature": float(T),
            "lambda_min": result["lambda_min"],
            "n_negative": result["n_negative"],
            "spinodal": result["spinodal"],
        }

        for i, eig in enumerate(result["eigenvalues"], start=1):
            row[f"lambda_{i}"] = float(eig)

        rows.append(row)

    return pd.DataFrame(rows)


def estimate_spinodal_temperature(df: pd.DataFrame) -> float | None:
    """
    Estimate the temperature where lambda_min crosses zero.
    Uses simple linear interpolation between adjacent points.
    """

    temps = df["temperature"].to_numpy(dtype=float)
    vals = df["lambda_min"].to_numpy(dtype=float)

    for i in range(len(vals) - 1):
        y1, y2 = vals[i], vals[i + 1]
        t1, t2 = temps[i], temps[i + 1]

        if y1 == 0:
            return float(t1)

        if y1 < 0 <= y2 or y2 < 0 <= y1:
            if abs(y2 - y1) < 1e-14:
                return float(t1)

            frac = -y1 / (y2 - y1)
            return float(t1 + frac * (t2 - t1))

    return None


def compute_mode_at_temperature(
    composition: list[str],
    mol_ratio: list[float],
    lattice: str,
    interaction_data: dict,
    temperature: float,
) -> dict:
    """
    Compute soft mode eigenvector at one temperature.
    """

    return spinodal_spectrum(
        composition=composition,
        temperature=temperature,
        lattice=lattice,
        mol=mol_ratio,
        interaction_data=interaction_data,
    )


def plot_eigenvalues_vs_temperature(
    df: pd.DataFrame,
    spinodal_temperature: float | None = None,
):
    fig, ax = plt.subplots(figsize=(5.5, 4.5))

    eigen_cols = sorted(
        [col for col in df.columns if col.startswith("lambda_") and col != "lambda_min"],
        key=lambda x: int(x.split("_")[1]),
    )

    for col in eigen_cols:
        ax.plot(df["temperature"], df[col], linewidth=1.6, label=col)

    ax.plot(
        df["temperature"],
        df["lambda_min"],
        linewidth=2.4,
        linestyle="--",
        label="lambda_min",
    )

    ax.axhline(0.0, linewidth=1.2)

    if spinodal_temperature is not None:
        ax.axvline(
            spinodal_temperature,
            linewidth=1.4,
            linestyle=":",
            label=f"T_spinodal ≈ {spinodal_temperature:.0f} K",
        )

    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Eigenvalue")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()

    return fig


def plot_mode_bar(
    composition: list[str],
    mode: list[float],
    temperature: float,
):
    fig, ax = plt.subplots(figsize=(5.5, 4.0))

    mode = np.asarray(mode, dtype=float)
    labels = list(composition)

    colors = ["tab:red" if x > 0 else "tab:blue" for x in mode]

    ax.bar(labels, mode, color=colors, edgecolor="black", linewidth=0.8)
    ax.axhline(0.0, linewidth=1.0)

    ax.set_ylabel("Soft mode amplitude")
    ax.set_title(f"Dominant spinodal mode at {temperature:.0f} K")
    fig.tight_layout()

    return fig


def interpret_mode(composition: list[str], mode: list[float]) -> dict:
    """
    Provide a simple sign-based interpretation.
    """

    positive = []
    negative = []
    near_zero = []

    for el, val in zip(composition, mode):
        if val > 1e-8:
            positive.append(el)
        elif val < -1e-8:
            negative.append(el)
        else:
            near_zero.append(el)

    return {
        "positive_group": positive,
        "negative_group": negative,
        "near_zero": near_zero,
    }