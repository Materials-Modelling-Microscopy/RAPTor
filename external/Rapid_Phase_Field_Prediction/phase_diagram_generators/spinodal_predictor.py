import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
from sympy import Matrix, Integer, symbols
from sympy.functions.elementary.exponential import log


KB_EV_PER_K = 8.617333262145e-5


_Q_PRECOMPUTED = np.array(
    [
        [-1, -1 / np.sqrt(3), -1 / np.sqrt(6), -1 / np.sqrt(10), -1 / np.sqrt(15), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [1, -1 / np.sqrt(3), -1 / np.sqrt(6), -1 / np.sqrt(10), -1 / np.sqrt(15), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 2 / np.sqrt(3), -1 / np.sqrt(6), -1 / np.sqrt(10), -1 / np.sqrt(15), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, np.sqrt(3) / np.sqrt(2), -1 / np.sqrt(10), -1 / np.sqrt(15), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, 0, 2 * np.sqrt(2) / np.sqrt(5), -1 / np.sqrt(15), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, 0, 0, np.sqrt(5) / np.sqrt(3), -1 / np.sqrt(21), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, 0, 0, 0, 2 * np.sqrt(3) / np.sqrt(7), -1 / (2 * np.sqrt(7)), -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, 0, 0, 0, 0, np.sqrt(7) / 2, -1 / 6, -1 / (3 * np.sqrt(5))],
        [0, 0, 0, 0, 0, 0, 0, 4 / 3, -1 / (3 * np.sqrt(5))],
    ],
    dtype=float,
)

LATTICE_ALIASES = {
    "BCC_A2": "BCC",
    "BCC": "BCC",
    "FCC_A1": "FCC",
    "FCC": "FCC",
    "HCP_A3": "HCP",
    "HCP": "HCP",
}


def load_interaction_data(path: str | Path) -> dict:
    """
    Load binary interaction parameters from JSON.

    Expected format:
    {
        "Ag-As": {
            "BCC": -0.1974,
            "FCC": -0.2388,
            "HCP": -0.3359
        }
    }
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Spinodal interaction data file not found: {path}")

    with open(path, "r") as f:
        return json.load(f)


def _normalize_element(element: str) -> str:
    element = str(element).strip()
    return element[0].upper() + element[1:].lower()


def _normalize_lattice(lattice: str) -> str:
    if lattice not in LATTICE_ALIASES:
        raise KeyError(
            f"Unknown lattice label: {lattice}. "
            f"Allowed: {list(LATTICE_ALIASES.keys())}"
        )

    return LATTICE_ALIASES[lattice]


def _get_omega(
    interaction_data: dict,
    element_a: str,
    element_b: str,
    lattice: str,
) -> float:
    """
    Retrieve Ω_ij for a binary pair and lattice.

    Handles both A-B and B-A ordering.
    Handles pycalphad-style lattice names like BCC_A2 by mapping to BCC.
    """

    a = _normalize_element(element_a)
    b = _normalize_element(element_b)

    lattice_key = _normalize_lattice(lattice)

    candidate_keys = [
        f"{a}-{b}",
        f"{b}-{a}",
        f"{a.upper()}-{b.upper()}",
        f"{b.upper()}-{a.upper()}",
    ]

    for pair_key in candidate_keys:
        if pair_key in interaction_data:
            pair_data = interaction_data[pair_key]

            if lattice_key not in pair_data:
                raise KeyError(
                    f"Found binary pair {pair_key}, but lattice {lattice_key} is missing. "
                    f"Available lattices: {list(pair_data.keys())}"
                )

            return float(pair_data[lattice_key])

    raise KeyError(
        f"Missing binary interaction for {a}-{b}. "
        f"Tried keys: {candidate_keys}"
    )


def create_xsyms(n: int):
    if n < 2:
        raise ValueError("Need at least two components.")

    return list(symbols(f"x1:{n}"))


def x_N(syms):
    xn = Integer(1)

    for sym in syms:
        xn -= sym

    return xn


def create_Ssym(xsyms, kb: float = KB_EV_PER_K):
    out = Integer(0)

    for x in xsyms:
        out += -kb * x * log(x + 1e-4)

    return out


def create_Hsym(xsyms, composition, interaction_data, lattice):
    """
    Regular-solution enthalpy:

        H_mix = sum_ij omega_ij x_i x_j
    """

    out = Integer(0)

    for i, j in itertools.combinations(range(len(composition)), 2):
        element_i = composition[i]
        element_j = composition[j]

        omega = _get_omega(
            interaction_data=interaction_data,
            element_a=element_i,
            element_b=element_j,
            lattice=lattice,
        )

        out += omega * xsyms[i] * xsyms[j]

    return out


def hessian(f, syms):
    return Matrix([[f.diff(x).diff(y) for x in syms] for y in syms])


def return_hessian(
    composition,
    mol,
    interaction_data,
    temperature,
    lattice,
    kb: float = KB_EV_PER_K,
):
    composition = list(composition)
    mol = np.asarray(mol, dtype=float)

    n = len(composition)

    if len(mol) != n:
        raise ValueError(
            f"mol length must match composition length. "
            f"Got mol={mol}, composition={composition}"
        )

    if not np.isclose(np.sum(mol), 1.0, atol=1e-4):
        raise ValueError(f"Composition must sum to 1. Got sum={np.sum(mol):.6f}")

    xsym = create_xsyms(n)
    xsyms = xsym + [x_N(xsym)]

    H_sym = create_Hsym(
        xsyms=xsyms,
        composition=composition,
        interaction_data=interaction_data,
        lattice=lattice,
    )

    S_sym = create_Ssym(xsyms, kb=kb)

    T = symbols("T")
    G = H_sym - T * S_sym

    H_reduced = hessian(G, xsym)

    independent_mol = list(mol[: n - 1])

    substitutions = list(zip(xsym + [T], independent_mol + [temperature]))

    H_num = H_reduced.subs(substitutions)

    return np.array(H_num, dtype=float)


def return_gibbs(
    composition,
    mol,
    interaction_data,
    temperature,
    lattice,
    kb: float = KB_EV_PER_K,
):
    composition = list(composition)
    mol = np.asarray(mol, dtype=float)

    n = len(composition)

    xsym = create_xsyms(n)
    xsyms = xsym + [x_N(xsym)]

    H_sym = create_Hsym(
        xsyms=xsyms,
        composition=composition,
        interaction_data=interaction_data,
        lattice=lattice,
    )

    S_sym = create_Ssym(xsyms, kb=kb)

    T = symbols("T")
    G = H_sym - T * S_sym

    independent_mol = list(mol[: n - 1])
    substitutions = list(zip(xsym + [T], independent_mol + [temperature]))

    return float(G.subs(substitutions))


def orthonormalization(H, n):
    """
    Transform the reduced Hessian to the composition-conserving subspace
    and return eigenvalues plus the full n-component eigenvector.
    """

    H = np.asarray(H, dtype=float)

    if n - 1 > _Q_PRECOMPUTED.shape[0]:
        raise ValueError(
            f"Orthonormalization currently supports up to "
            f"{_Q_PRECOMPUTED.shape[0] + 1} components."
        )

    Q = _Q_PRECOMPUTED[: n - 1, : n - 1]

    H_cap = Q.T @ H @ Q
    H_cap = 0.5 * (H_cap + H_cap.T)

    eigvals, eigvecs_red = np.linalg.eigh(H_cap)

    min_idx = int(np.argmin(eigvals))

    eigenvec_gibbs = Q @ eigvecs_red[:, min_idx]
    final_component = -np.sum(eigenvec_gibbs)

    full_mode = np.array(
        list(eigenvec_gibbs) + [final_component],
        dtype=float,
    )

    norm = np.linalg.norm(full_mode)
    if norm > 0:
        full_mode = full_mode / norm

    return eigvals, full_mode


def spinodal_spectrum(
    composition,
    temperature,
    lattice,
    mol,
    interaction_data,
    kb: float = KB_EV_PER_K,
    negative_tolerance: float = -1e-8,
) -> dict[str, Any]:
    """
    Return the full spinodal spectrum at a given composition and temperature.
    """

    n = len(composition)

    H_gibbs = return_hessian(
        composition=composition,
        mol=mol,
        interaction_data=interaction_data,
        temperature=temperature,
        lattice=lattice,
        kb=kb,
    )

    eigenvalues, eigenvector = orthonormalization(H_gibbs, n)

    eigenvalues = np.sort(np.asarray(eigenvalues, dtype=float))
    lambda_min = float(np.min(eigenvalues))
    n_negative = int(np.sum(eigenvalues < negative_tolerance))

    return {
        "eigenvalues": eigenvalues.tolist(),
        "lambda_min": lambda_min,
        "n_negative": n_negative,
        "spinodal": bool(lambda_min < negative_tolerance),
        "mode": np.asarray(eigenvector, dtype=float).tolist(),
    }


def predict_spinodal(
    composition,
    temperature,
    lattice,
    mol,
    interaction_data,
    kb: float = KB_EV_PER_K,
    negative_tolerance: float = -1e-8,
) -> dict[str, Any]:
    """
    Backward-compatible summary wrapper.
    """
    result = spinodal_spectrum(
        composition=composition,
        temperature=temperature,
        lattice=lattice,
        mol=mol,
        interaction_data=interaction_data,
        kb=kb,
        negative_tolerance=negative_tolerance,
    )

    return {
        "lambda_min": result["lambda_min"],
        "n_negative": result["n_negative"],
        "spinodal": result["spinodal"],
        "mode": result["mode"],
    }
