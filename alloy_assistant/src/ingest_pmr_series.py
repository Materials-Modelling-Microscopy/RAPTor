"""Ingest binary through quinary percentage-miscible-region data."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT
from .ingestion_common import (
    ensure_staging_schema,
    register_source,
    source_exists,
    source_identity,
    transaction,
    upsert_model,
    upsert_system,
)
from .normalization import canonical_elements, stable_id


COMPUTATIONAL_ROOT = (
    ALLOY_ASSISTANT_ROOT / "data" / "inbox" / "computational_results"
)
PMR_FILES = {
    2: COMPUTATIONAL_ROOT / "binary_PMR.csv",
    3: COMPUTATIONAL_ROOT / "ternary_PMR.csv",
    4: COMPUTATIONAL_ROOT / "quaternary_PMR.csv",
    5: COMPUTATIONAL_ROOT / "quinary_PMR.csv",
}
MODEL_ID = "model_pmr_grid_0p1_legacy"
TEMPERATURE_COLUMNS = {
    "500K": 500.0,
    "1000K": 1000.0,
    "1500K": 1500.0,
}


@dataclass(frozen=True)
class PmrIngestionReport:
    files_ingested: int
    files_already_ingested: int
    staged_rows: int
    pmr_predictions: int


def _ingest_file(
    connection: DuckDBPyConnection,
    *,
    n_components: int,
    path: Path,
) -> tuple[bool, int]:
    source_id, checksum = source_identity(path)
    if source_exists(connection, sha256=checksum):
        return False, 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No rows in {path}")

    with transaction(connection):
        register_source(
            connection,
            path=path,
            source_id=source_id,
            sha256=checksum,
            source_class="computational_dataset",
            title=f"{n_components}-component PMR at 500, 1000, and 1500 K",
            authority_status="authoritative_curated",
            notes=(
                "PMR is percentage miscible region on a composition grid "
                "with 0.1 atomic-fraction spacing. Legacy condition is staged "
                "but not curated."
            ),
        )
        upsert_model(
            connection,
            model_id=MODEL_ID,
            model_name="Legacy PMR grid workflow",
            description=(
                "Percentage miscible region calculated on a composition grid "
                "with 0.1 atomic-fraction spacing."
            ),
        )

        seen_systems: set[tuple[str, ...]] = set()
        for source_row_number, row in enumerate(rows, start=2):
            elements = canonical_elements(tuple(row["Alloy"].split("-")))
            if len(elements) != n_components:
                raise ValueError(
                    f"Row {source_row_number}: expected {n_components} "
                    f"components, found {elements}"
                )
            if elements in seen_systems:
                raise ValueError(
                    f"Row {source_row_number}: duplicate PMR system {elements}"
                )
            seen_systems.add(elements)
            system_identifier = upsert_system(connection, elements)

            percentages = {
                column: float(row[column])
                for column in TEMPERATURE_COLUMNS
            }
            if any(value < 0 or value > 100 for value in percentages.values()):
                raise ValueError(
                    f"Row {source_row_number}: PMR must be between 0 and 100"
                )

            condition_text = (row.get("condition") or "").strip()
            condition = float(condition_text) if condition_text else None
            connection.execute(
                """
                INSERT INTO staging.pmr_data_raw
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source_id,
                    source_row_number,
                    int(row[""] if "" in row else row["Unnamed: 0"]),
                    n_components,
                    row["Alloy"],
                    percentages["500K"],
                    percentages["1000K"],
                    percentages["1500K"],
                    condition,
                ],
            )

            run_id = stable_id("run", source_id, row["Alloy"], "pmr")
            connection.execute(
                """
                INSERT INTO alloy.calculation_runs (
                    run_id,
                    model_id,
                    composition_id,
                    system_id,
                    tdb_source_id,
                    result_source_id,
                    settings_json,
                    run_timestamp
                )
                VALUES (?, ?, NULL, ?, NULL, ?, ?, NULL)
                """,
                [
                    run_id,
                    MODEL_ID,
                    system_identifier,
                    source_id,
                    json.dumps(
                        {
                            "grid_spacing_atomic_fraction": 0.1,
                            "n_components": n_components,
                            "source_format": "legacy_csv",
                        },
                        sort_keys=True,
                    ),
                ],
            )

            for column, temperature in TEMPERATURE_COLUMNS.items():
                connection.execute(
                    """
                    INSERT INTO alloy.pmr_predictions (
                        pmr_prediction_id,
                        run_id,
                        system_id,
                        temperature_K,
                        pmr_percent,
                        grid_spacing_atomic_fraction,
                        source_row_number,
                        quality_flag
                    )
                    VALUES (?, ?, ?, ?, ?, 0.1, ?, 'validated')
                    """,
                    [
                        stable_id(
                            "pmr",
                            run_id,
                            str(int(temperature)),
                        ),
                        run_id,
                        system_identifier,
                        temperature,
                        percentages[column],
                        source_row_number,
                    ],
                )

    return True, len(rows)


def ingest_pmr_series(connection: DuckDBPyConnection) -> PmrIngestionReport:
    ensure_staging_schema(connection)
    ingested = 0
    existing = 0
    staged = 0
    for n_components, path in PMR_FILES.items():
        was_ingested, rows = _ingest_file(
            connection,
            n_components=n_components,
            path=path,
        )
        if was_ingested:
            ingested += 1
            staged += rows
        else:
            existing += 1

    prediction_count = int(
        connection.execute(
            "SELECT count(*) FROM alloy.pmr_predictions"
        ).fetchone()[0]
    )
    return PmrIngestionReport(
        files_ingested=ingested,
        files_already_ingested=existing,
        staged_rows=staged,
        pmr_predictions=prediction_count,
    )

