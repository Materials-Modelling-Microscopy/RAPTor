from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from pycalphad import Database

from alloy_web.config import ensure_project_imports


ensure_project_imports()

from alloy_web.adapters.alloy_summary_adapter import (
    _resolve_tdb_path,
    _tdb_index,
    evaluate_equimolar_state,
    sample_miscible_region,
    scan_miscibility_temperature,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_analysis import (
    compute_spinodal_vs_temperature,
    estimate_spinodal_temperature,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_predictor import (
    load_interaction_data,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.pathway_analysis import (
    analyze_processing_paths,
)
from external.Rapid_Phase_Field_Prediction.utils.combination_generation import (
    MultinaryCombinations,
)


MISCIBILITY_TEMPERATURE = "miscibility_temperature"
SPINODAL_TEMPERATURE = "spinodal_temperature"
PMR = "pmr"
EQUIMOLAR_SOLID_SOLUTION_FRACTION = "equimolar_solid_solution_fraction"
ACTIVE_PHASE_COUNT = "active_phase_count"
METASTABILITY_GAP = "metastability_gap"
MEAN_PATH_BURDEN = "mean_path_burden"
PATH_BURDEN_VARIANCE = "path_burden_variance"


@dataclass(frozen=True)
class MetricDefinition:
    label: str
    unit: str
    favorable: str
    description: str


METRICS: dict[str, MetricDefinition] = {
    MISCIBILITY_TEMPERATURE: MetricDefinition(
        "Miscibility temperature", "K", "lower",
        "Lowest temperature where the equimolar alloy is at least 99% one solid solution.",
    ),
    SPINODAL_TEMPERATURE: MetricDefinition(
        "Spinodal temperature", "K", "context",
        "Temperature where the equimolar solution changes from locally unstable to stable; excluded from Pareto optimization because the preferred direction depends on the design goal.",
    ),
    PMR: MetricDefinition(
        "Percentage miscible region (PMR)", "%", "higher",
        "Share of sampled compositions that are at least 99% one solid solution.",
    ),
    EQUIMOLAR_SOLID_SOLUTION_FRACTION: MetricDefinition(
        "Equimolar solid-solution fraction", "%", "higher",
        "Largest individual BCC_A2, FCC_A1, or HCP_A3 fraction at the reference temperature.",
    ),
    ACTIVE_PHASE_COUNT: MetricDefinition(
        "Active phase count", "", "lower",
        "Number of active equilibrium composition sets at the equimolar composition.",
    ),
    METASTABILITY_GAP: MetricDefinition(
        "Metastability gap", "K", "lower",
        "Miscibility temperature minus spinodal temperature for the equimolar alloy, bounded at zero.",
    ),
    MEAN_PATH_BURDEN: MetricDefinition(
        "Mean integrated path burden", "meV/atom", "context",
        "Mean path integral of equimolar BCC_A2 energy above the equilibrium hull across every unique sequential alloying route.",
    ),
    PATH_BURDEN_VARIANCE: MetricDefinition(
        "Path-burden variance", "(meV/atom)²", "context",
        "Variance between the integrated burdens of unique sequential alloying routes; no universally favorable direction is assigned.",
    ),
}


@dataclass
class MetricValue:
    value: float | None
    display: str
    status: str
    phase: str | None = None
    details: dict | None = None
    calculation_count: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class InterSystemComparisonResult:
    data: pd.DataFrame
    selected_metrics: list[str]
    pareto_metrics: list[str]
    primary_metric: str
    candidate_count: int
    complete_count: int
    pareto_count: int
    cache_hits: int
    cache_misses: int
    equilibrium_calculations: int
    elapsed_seconds: float

    def to_csv_bytes(self) -> bytes:
        output = self.data.copy()
        for metric in self.selected_metrics:
            output[METRICS[metric].label] = output[f"{metric}__display"]
        hidden = [
            column for column in output.columns
            if column.endswith("__display") or column in self.selected_metrics
        ]
        return output.drop(columns=hidden).to_csv(index=False).encode("utf-8")


class MetricCache:
    """A settings- and source-aware SQLite cache for expensive metric evaluations."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0)
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_cache (
                system_key TEXT NOT NULL,
                metric TEXT NOT NULL,
                settings_key TEXT NOT NULL,
                source_signature TEXT NOT NULL,
                value REAL,
                display TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT,
                details_json TEXT NOT NULL,
                calculation_count INTEGER NOT NULL,
                elapsed_seconds REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (system_key, metric, settings_key, source_signature)
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def settings_key(settings: dict) -> str:
        return json.dumps(settings, sort_keys=True, separators=(",", ":"))

    def get(
        self,
        system_key: str,
        metric: str,
        settings: dict,
        source_signature: str,
    ) -> MetricValue | None:
        row = self.connection.execute(
            """
            SELECT value, display, status, phase, details_json
            FROM metric_cache
            WHERE system_key = ? AND metric = ? AND settings_key = ?
              AND source_signature = ?
            """,
            (system_key, metric, self.settings_key(settings), source_signature),
        ).fetchone()
        if row is None:
            return None
        return MetricValue(
            value=row[0], display=row[1], status=row[2], phase=row[3],
            details=json.loads(row[4]), calculation_count=0, elapsed_seconds=0.0,
        )

    def put(
        self,
        system_key: str,
        metric: str,
        settings: dict,
        source_signature: str,
        result: MetricValue,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO metric_cache (
                system_key, metric, settings_key, source_signature, value, display,
                status, phase, details_json, calculation_count, elapsed_seconds, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                system_key, metric, self.settings_key(settings), source_signature,
                result.value, result.display, result.status, result.phase,
                json.dumps(result.details or {}, sort_keys=True),
                result.calculation_count, result.elapsed_seconds,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def generate_candidate_systems(element_pool: list[str], order: int) -> list[tuple[str, ...]]:
    """Use the project's existing multinary generator and preserve selector order."""
    if order < 2 or order > len(element_pool):
        raise ValueError("System order must be between 2 and the element-pool size.")
    generated = MultinaryCombinations.generate_combinations(
        element_pool, order, sort=False
    )
    order_lookup = {element: position for position, element in enumerate(element_pool)}
    systems = [tuple(system.split("-")) for system in generated]
    return sorted(
        systems,
        key=lambda system: tuple(order_lookup[element] for element in system),
    )


def pareto_optimal_mask(data: pd.DataFrame, metrics: Iterable[str]) -> pd.Series:
    metric_list = list(metrics)
    mask = pd.Series(False, index=data.index, dtype=bool)
    if not metric_list:
        return mask

    complete = data[metric_list].notna().all(axis=1)
    complete_index = data.index[complete]
    if complete_index.empty:
        return mask

    values = data.loc[complete_index, metric_list].to_numpy(dtype=float, copy=True)
    for column, metric in enumerate(metric_list):
        if METRICS[metric].favorable == "lower":
            values[:, column] *= -1.0

    optimal = np.ones(len(values), dtype=bool)
    for position, candidate in enumerate(values):
        dominated = np.any(
            np.all(values >= candidate, axis=1)
            & np.any(values > candidate, axis=1)
        )
        optimal[position] = not dominated
    mask.loc[complete_index] = optimal
    return mask


def _source_signature(path: Path | None, missing_parent: Path | None = None) -> str:
    if path is not None and path.exists():
        stat = path.stat()
        return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    if missing_parent is not None and missing_parent.exists():
        stat = missing_parent.stat()
        return f"missing:{stat.st_mtime_ns}"
    return "missing"


def _temperature_result(
    value: float | None,
    bound: str,
    temperature_min: float,
    temperature_max: float,
) -> tuple[float | None, str, str]:
    if value is None:
        return None, f"Not found through {temperature_max:.0f} K", "unavailable"
    if bound == "at_or_below_minimum":
        return float(temperature_min), f"≤ {temperature_min:.0f} K", "bounded"
    return float(value), f"{value:.0f} K", "ok"


def _metastability_gap(
    miscibility_temperature: float,
    spinodal_temperature: float,
) -> float:
    return max(0.0, miscibility_temperature - spinodal_temperature)


def run_inter_system_comparison(
    element_pool: list[str],
    order: int,
    selected_metrics: list[str],
    primary_metric: str,
    reference_temperature: float,
    temperature_min: float,
    temperature_max: float,
    temperature_step: float,
    lattice: str,
    tdb_dir: str | Path,
    interaction_data_path: str | Path,
    cache_path: str | Path,
    miscibility_threshold: float = 0.99,
    max_sample_points: int = 400,
    pathway_points_per_segment: int = 5,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> InterSystemComparisonResult:
    started_at = perf_counter()
    if len(set(element_pool)) != len(element_pool):
        raise ValueError("Element-pool entries must be unique.")
    if not selected_metrics or any(metric not in METRICS for metric in selected_metrics):
        raise ValueError("Choose at least one supported comparison property.")
    if primary_metric not in selected_metrics:
        raise ValueError("The primary ranking property must be selected.")
    if temperature_min >= temperature_max or temperature_step <= 0:
        raise ValueError("Use a valid increasing temperature range and positive step.")
    pathway_metrics = {MEAN_PATH_BURDEN, PATH_BURDEN_VARIANCE}
    if set(selected_metrics) & pathway_metrics:
        if order < 3:
            raise ValueError("Path-burden comparison requires ternary or higher-order systems.")
        if pathway_points_per_segment < 2:
            raise ValueError("Use at least two points per pathway segment.")

    systems = generate_candidate_systems(element_pool, order)
    tdb_dir = Path(tdb_dir)
    interaction_data_path = Path(interaction_data_path)
    tdb_index = _tdb_index(tdb_dir)
    interaction_signature = _source_signature(interaction_data_path)
    database_cache: dict[Path, Database] = {}
    interaction_data: dict | None = None
    cache_hits = 0
    cache_misses = 0
    calculations = 0
    rows: list[dict] = []

    miscibility_settings = {
        "temperature_min": float(temperature_min),
        "temperature_max": float(temperature_max),
        "temperature_step": float(temperature_step),
        "threshold": float(miscibility_threshold),
    }
    spinodal_settings = {
        "temperature_min": float(temperature_min),
        "temperature_max": float(temperature_max),
        "temperature_step": float(temperature_step),
        "lattice": lattice,
    }
    pmr_settings = {
        "reference_temperature": float(reference_temperature),
        "threshold": float(miscibility_threshold),
        "max_sample_points": int(max_sample_points),
    }
    equimolar_settings = {"reference_temperature": float(reference_temperature)}
    pathway_settings = {
        "reference_temperature": float(reference_temperature),
        "points_per_segment": int(pathway_points_per_segment),
        "definition_version": 1,
    }

    with MetricCache(cache_path) as cache:
        for completed, system in enumerate(systems, start=1):
            system_key = "-".join(system)
            tdb_path = _resolve_tdb_path(system, tdb_dir, tdb_index)
            tdb_signature = _source_signature(tdb_path, tdb_dir)
            current: dict[str, MetricValue] = {}

            def cached_or_compute(
                metric: str,
                settings: dict,
                signature: str,
                compute: Callable[[], MetricValue],
            ) -> MetricValue:
                nonlocal cache_hits, cache_misses, calculations
                if metric in current:
                    return current[metric]
                cached = cache.get(system_key, metric, settings, signature)
                if cached is not None:
                    cache_hits += 1
                    current[metric] = cached
                    return cached
                cache_misses += 1
                metric_started = perf_counter()
                try:
                    result = compute()
                except Exception as exc:
                    result = MetricValue(
                        None, f"Calculation failed: {exc}", "failed",
                        details={"error": str(exc)},
                    )
                result.elapsed_seconds = perf_counter() - metric_started
                calculations += result.calculation_count
                cache.put(system_key, metric, settings, signature, result)
                current[metric] = result
                return result

            def database() -> Database:
                if tdb_path is None:
                    raise FileNotFoundError("TDB unavailable")
                if tdb_path not in database_cache:
                    database_cache[tdb_path] = Database(str(tdb_path))
                return database_cache[tdb_path]

            def miscibility() -> MetricValue:
                scan = scan_miscibility_temperature(
                    db=database(), elements=system,
                    reference_temperature=reference_temperature,
                    temperature_min=temperature_min,
                    temperature_max=temperature_max,
                    temperature_step=temperature_step,
                    threshold=miscibility_threshold,
                )
                value, display, status = _temperature_result(
                    scan["miscibility_temperature"], scan["temperature_bound"],
                    temperature_min, temperature_max,
                )
                return MetricValue(
                    value, display, status, phase=scan["miscibility_phase"],
                    details={"active_phases_at_reference": scan["reference_active_phases"]},
                    calculation_count=scan["calculation_count"],
                )

            def spinodal() -> MetricValue:
                nonlocal interaction_data
                if interaction_data is None:
                    interaction_data = load_interaction_data(interaction_data_path)
                spectrum = compute_spinodal_vs_temperature(
                    composition=list(system),
                    mol_ratio=[1.0 / len(system)] * len(system),
                    lattice=lattice,
                    interaction_data=interaction_data,
                    temperature_min=temperature_min,
                    temperature_max=temperature_max,
                    temperature_step=temperature_step,
                )
                estimate = estimate_spinodal_temperature(spectrum)
                first = float(spectrum["lambda_min"].iloc[0])
                last = float(spectrum["lambda_min"].iloc[-1])
                if estimate is not None:
                    value, display, status = float(estimate), f"{estimate:.0f} K", "ok"
                elif first >= 0.0:
                    value, display, status = temperature_min, f"≤ {temperature_min:.0f} K", "bounded"
                elif last < 0.0:
                    value, display, status = None, f"Not found through {temperature_max:.0f} K", "unavailable"
                else:
                    value, display, status = None, "No crossing found", "unavailable"
                return MetricValue(
                    value, display, status,
                    details={"lambda_min_at_min": first, "lambda_min_at_max": last},
                    calculation_count=len(spectrum),
                )

            def pmr() -> MetricValue:
                sample = sample_miscible_region(
                    db=database(), elements=list(system),
                    reference_temperature=reference_temperature,
                    threshold=miscibility_threshold,
                    max_points=max_sample_points,
                )
                value = float(sample["percentage"])
                return MetricValue(
                    value, f"{value:.1f}%", "ok",
                    details={
                        "compositions": sample["grid_points"],
                        "evaluated": sample["evaluated"],
                        "miscible": sample["miscible"],
                    },
                    calculation_count=sample["calculation_count"],
                )

            def equimolar_state() -> tuple[MetricValue, MetricValue]:
                state = evaluate_equimolar_state(
                    database(), system, reference_temperature
                )
                fraction = 100.0 * float(state["largest_solid_solution_fraction"])
                common_details = {"active_phases": state["active_phases"]}
                fraction_result = MetricValue(
                    fraction, f"{fraction:.1f}%", "ok",
                    phase=state["largest_solid_solution_phase"],
                    details=common_details,
                    calculation_count=state["calculation_count"],
                )
                phase_count = float(state["active_phase_count"])
                count_result = MetricValue(
                    phase_count, f"{phase_count:.0f}", "ok",
                    details=common_details, calculation_count=0,
                )
                return fraction_result, count_result

            def get_equimolar_metric(metric: str) -> MetricValue:
                nonlocal cache_hits, cache_misses, calculations
                if metric in current:
                    return current[metric]
                cached = cache.get(system_key, metric, equimolar_settings, tdb_signature)
                if cached is not None:
                    cache_hits += 1
                    current[metric] = cached
                    return cached

                fraction_cached = cache.get(
                    system_key, EQUIMOLAR_SOLID_SOLUTION_FRACTION,
                    equimolar_settings, tdb_signature,
                )
                count_cached = cache.get(
                    system_key, ACTIVE_PHASE_COUNT, equimolar_settings, tdb_signature,
                )
                if fraction_cached is not None and count_cached is not None:
                    cache_hits += 1
                    current[EQUIMOLAR_SOLID_SOLUTION_FRACTION] = fraction_cached
                    current[ACTIVE_PHASE_COUNT] = count_cached
                    return current[metric]

                cache_misses += 1
                metric_started = perf_counter()
                try:
                    fraction_result, count_result = equimolar_state()
                except Exception as exc:
                    failure = MetricValue(
                        None, f"Calculation failed: {exc}", "failed",
                        details={"error": str(exc)},
                    )
                    fraction_result = failure
                    count_result = MetricValue(**failure.__dict__)
                elapsed = perf_counter() - metric_started
                fraction_result.elapsed_seconds = elapsed
                count_result.elapsed_seconds = elapsed
                calculations += fraction_result.calculation_count
                for key, result in (
                    (EQUIMOLAR_SOLID_SOLUTION_FRACTION, fraction_result),
                    (ACTIVE_PHASE_COUNT, count_result),
                ):
                    cache.put(system_key, key, equimolar_settings, tdb_signature, result)
                    current[key] = result
                return current[metric]

            def pathway_state() -> tuple[MetricValue, MetricValue]:
                if tdb_path is None:
                    raise FileNotFoundError("TDB unavailable")
                analysis = analyze_processing_paths(
                    tdb_path=tdb_path,
                    target_composition={
                        element: 1.0 / len(system)
                        for element in system
                    },
                    temperature=reference_temperature,
                    points_per_segment=pathway_points_per_segment,
                )
                metrics = analysis["system_metrics"]
                path_count = len(analysis["paths"])
                composition_columns = [
                    column for column in analysis["path_points"].columns
                    if column.startswith("X_")
                ]
                calculation_count = len(
                    analysis["path_points"][composition_columns].drop_duplicates()
                )
                details = {"path_count": path_count}
                mean_value = metrics[
                    "mean_integrated_burden_meV_per_atom"
                ]
                variance_value = metrics[
                    "path_dependence_variance_meV2_per_atom2"
                ]
                return (
                    MetricValue(
                        mean_value, f"{mean_value:.2f} meV/atom", "ok",
                        details=details, calculation_count=calculation_count,
                    ),
                    MetricValue(
                        variance_value, f"{variance_value:.2f} (meV/atom)²", "ok",
                        details=details,
                    ),
                )

            def get_pathway_metric(metric: str) -> MetricValue:
                nonlocal cache_hits, cache_misses, calculations
                if metric in current:
                    return current[metric]
                cached = cache.get(
                    system_key, metric, pathway_settings, tdb_signature
                )
                if cached is not None:
                    cache_hits += 1
                    current[metric] = cached
                    return cached

                mean_cached = cache.get(
                    system_key, MEAN_PATH_BURDEN,
                    pathway_settings, tdb_signature,
                )
                variance_cached = cache.get(
                    system_key, PATH_BURDEN_VARIANCE,
                    pathway_settings, tdb_signature,
                )
                if mean_cached is not None and variance_cached is not None:
                    cache_hits += 1
                    current[MEAN_PATH_BURDEN] = mean_cached
                    current[PATH_BURDEN_VARIANCE] = variance_cached
                    return current[metric]

                cache_misses += 1
                metric_started = perf_counter()
                try:
                    mean_result, variance_result = pathway_state()
                except Exception as exc:
                    failure = MetricValue(
                        None, f"Calculation failed: {exc}", "failed",
                        details={"error": str(exc)},
                    )
                    mean_result = failure
                    variance_result = MetricValue(**failure.__dict__)
                elapsed = perf_counter() - metric_started
                mean_result.elapsed_seconds = elapsed
                variance_result.elapsed_seconds = elapsed
                calculations += mean_result.calculation_count
                for key, result in (
                    (MEAN_PATH_BURDEN, mean_result),
                    (PATH_BURDEN_VARIANCE, variance_result),
                ):
                    cache.put(
                        system_key, key, pathway_settings,
                        tdb_signature, result,
                    )
                    current[key] = result
                return current[metric]

            def metric_value(metric: str) -> MetricValue:
                if metric == MISCIBILITY_TEMPERATURE:
                    return cached_or_compute(
                        metric, miscibility_settings, tdb_signature, miscibility
                    )
                if metric == SPINODAL_TEMPERATURE:
                    return cached_or_compute(
                        metric, spinodal_settings, interaction_signature, spinodal
                    )
                if metric == PMR:
                    return cached_or_compute(metric, pmr_settings, tdb_signature, pmr)
                if metric in {
                    EQUIMOLAR_SOLID_SOLUTION_FRACTION, ACTIVE_PHASE_COUNT
                }:
                    return get_equimolar_metric(metric)
                if metric == METASTABILITY_GAP:
                    gap_settings = {
                        "miscibility": miscibility_settings,
                        "spinodal": spinodal_settings,
                        "definition_version": 2,
                    }

                    def gap() -> MetricValue:
                        misc = metric_value(MISCIBILITY_TEMPERATURE)
                        spin = metric_value(SPINODAL_TEMPERATURE)
                        if misc.value is None or spin.value is None:
                            return MetricValue(
                                None, "Unavailable", "unavailable",
                                details={"miscibility": misc.display, "spinodal": spin.display},
                            )
                        raw_value = misc.value - spin.value
                        value = _metastability_gap(misc.value, spin.value)
                        return MetricValue(
                            value, f"{value:.0f} K", "ok",
                            details={
                                "miscibility": misc.display,
                                "spinodal": spin.display,
                                "unbounded_gap": raw_value,
                            },
                        )

                    return cached_or_compute(
                        metric, gap_settings,
                        f"{tdb_signature}|{interaction_signature}", gap,
                    )
                if metric in pathway_metrics:
                    return get_pathway_metric(metric)
                raise KeyError(metric)

            row: dict = {"System": system_key}
            statuses = []
            phases = []
            for metric in selected_metrics:
                result = metric_value(metric)
                row[metric] = result.value
                row[f"{metric}__display"] = result.display
                if result.phase:
                    phases.append(result.phase)
                if result.status in {"failed", "unavailable"}:
                    statuses.append(METRICS[metric].label)
            row["Solid solution phase"] = ", ".join(dict.fromkeys(phases)) or None
            row["Data status"] = (
                "Complete" if not statuses else f"Unavailable: {', '.join(statuses)}"
            )
            rows.append(row)
            if progress_callback is not None:
                progress_callback(completed, len(systems), system_key)

    data = pd.DataFrame(rows)
    pareto_metrics = [
        metric for metric in selected_metrics
        if METRICS[metric].favorable in {"lower", "higher"}
    ]
    data["Pareto optimal"] = pareto_optimal_mask(data, pareto_metrics)
    primary_direction = METRICS[primary_metric].favorable
    if primary_direction == "context":
        data["Rank"] = pd.Series(pd.NA, index=data.index, dtype="Int64")
        data = data.sort_values("System").reset_index(drop=True)
    else:
        ascending = primary_direction == "lower"
        ranks = data[primary_metric].rank(
            method="min", ascending=ascending, na_option="keep"
        )
        data["Rank"] = ranks.astype("Int64")
        data = data.sort_values(
            [primary_metric, "System"],
            ascending=[ascending, True],
            na_position="last",
        ).reset_index(drop=True)

    return InterSystemComparisonResult(
        data=data,
        selected_metrics=list(selected_metrics),
        pareto_metrics=pareto_metrics,
        primary_metric=primary_metric,
        candidate_count=len(data),
        complete_count=int(data[selected_metrics].notna().all(axis=1).sum()),
        pareto_count=int(data["Pareto optimal"].sum()),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        equilibrium_calculations=calculations,
        elapsed_seconds=perf_counter() - started_at,
    )
