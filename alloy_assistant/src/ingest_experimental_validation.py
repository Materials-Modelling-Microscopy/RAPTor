"""Ingest the curated refractory-HEA experimental validation table."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT
from .ingestion_common import (
    ensure_staging_schema,
    register_source,
    source_exists,
    source_identity,
    transaction,
    upsert_composition,
    upsert_model,
)
from .normalization import (
    is_equimolar,
    parse_composition_formula,
    stable_id,
)


SOURCE_PATH = (
    ALLOY_ASSISTANT_ROOT
    / "data"
    / "inbox"
    / "experimental_validation"
    / "refractory_hea_validation.csv"
)
MODEL_ID = "model_validation_miscibility_legacy"


@dataclass(frozen=True)
class ExperimentalValidationReport:
    already_ingested: bool
    staged_rows: int
    substantive_rows: int
    samples: int
    processing_events: int
    phase_observations: int
    miscibility_predictions: int


def _optional_float(value: str | None) -> float | None:
    text = (value or "").strip()
    return None if not text else float(text)


def _counts(
    connection: DuckDBPyConnection,
    *,
    source_id: str,
    already_ingested: bool,
) -> ExperimentalValidationReport:
    staged, substantive = connection.execute(
        """
        SELECT
            count(*),
            count(*) FILTER (WHERE row_status = 'substantive')
        FROM staging.experimental_validation_raw
        WHERE source_id = ?
        """,
        [source_id],
    ).fetchone()
    samples = int(
        connection.execute(
            "SELECT count(*) FROM alloy.experimental_samples WHERE source_id = ?",
            [source_id],
        ).fetchone()[0]
    )
    processing = int(
        connection.execute(
            """
            SELECT count(*)
            FROM alloy.processing_events AS pe
            JOIN alloy.experimental_samples AS es USING (sample_id)
            WHERE es.source_id = ?
            """,
            [source_id],
        ).fetchone()[0]
    )
    observations = int(
        connection.execute(
            """
            SELECT count(*)
            FROM alloy.experimental_phase_observations AS epo
            JOIN alloy.experimental_samples AS es USING (sample_id)
            WHERE es.source_id = ?
            """,
            [source_id],
        ).fetchone()[0]
    )
    predictions = int(
        connection.execute(
            """
            SELECT count(*)
            FROM alloy.miscibility_predictions AS mp
            JOIN alloy.calculation_runs AS cr USING (run_id)
            WHERE cr.result_source_id = ?
              AND cr.model_id = ?
            """,
            [source_id, MODEL_ID],
        ).fetchone()[0]
    )
    return ExperimentalValidationReport(
        already_ingested=already_ingested,
        staged_rows=int(staged),
        substantive_rows=int(substantive),
        samples=samples,
        processing_events=processing,
        phase_observations=observations,
        miscibility_predictions=predictions,
    )


def ingest_experimental_validation(
    connection: DuckDBPyConnection,
) -> ExperimentalValidationReport:
    ensure_staging_schema(connection)
    source_id, checksum = source_identity(SOURCE_PATH)
    existing = source_exists(connection, sha256=checksum)
    if existing is not None:
        return _counts(
            connection,
            source_id=existing,
            already_ingested=True,
        )

    with SOURCE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    with transaction(connection):
        register_source(
            connection,
            path=SOURCE_PATH,
            source_id=source_id,
            sha256=checksum,
            source_class="experimental_dataset",
            title="Curated refractory HEA experimental validation",
            authority_status="authoritative_curated",
            notes=(
                "Author-reviewed validation table. Publication mapping is "
                "pending. Duplicate source rows remain distinct samples."
            ),
        )
        upsert_model(
            connection,
            model_id=MODEL_ID,
            model_name="Legacy validation-table miscibility prediction",
            description=(
                "Predicted miscibility temperatures recorded alongside the "
                "author-curated experimental validation table."
            ),
        )

        for source_row_number, row in enumerate(rows, start=2):
            composition_raw = (row["Composition"] or "").strip()
            phases_raw = (row["Expt. Reported Phases"] or "").strip()
            processing_raw = (row["Processing"] or "").strip()
            processing_temperature = _optional_float(row["Processing. Temp"])
            predicted_tmisc = _optional_float(row["Predicted Miscible Temp"])
            trailing = (row.get("Unnamed: 5") or "").strip() or None
            row_status = "substantive" if composition_raw else "non_data"

            connection.execute(
                """
                INSERT INTO staging.experimental_validation_raw
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source_id,
                    source_row_number,
                    composition_raw or None,
                    phases_raw or None,
                    processing_raw or None,
                    processing_temperature,
                    predicted_tmisc,
                    trailing,
                    row_status,
                ],
            )
            if row_status == "non_data":
                continue
            if not phases_raw:
                raise ValueError(
                    f"Row {source_row_number}: reported phases are required"
                )
            if predicted_tmisc is None or predicted_tmisc < 0:
                raise ValueError(
                    f"Row {source_row_number}: invalid predicted T_misc"
                )

            fractions = parse_composition_formula(composition_raw)
            locator = f"csv-row:{source_row_number}"
            composition = upsert_composition(
                connection,
                fractions=fractions,
                original_formula=composition_raw,
                source_id=source_id,
                source_locator=locator,
                is_equimolar=is_equimolar(fractions),
            )
            sample_id = stable_id("sample", source_id, str(source_row_number))
            connection.execute(
                """
                INSERT INTO alloy.experimental_samples (
                    sample_id,
                    composition_id,
                    source_id,
                    source_locator,
                    sample_label,
                    provenance_status
                )
                VALUES (?, ?, ?, ?, ?, 'publication_mapping_pending')
                """,
                [
                    sample_id,
                    composition,
                    source_id,
                    locator,
                    f"{composition_raw} row {source_row_number}",
                ],
            )

            if processing_raw:
                connection.execute(
                    """
                    INSERT INTO alloy.processing_events (
                        processing_event_id,
                        sample_id,
                        sequence_number,
                        route,
                        temperature_K,
                        duration_s,
                        cooling_rate_K_s,
                        raw_processing_label,
                        notes
                    )
                    VALUES (?, ?, 1, ?, ?, NULL, NULL, ?, NULL)
                    """,
                    [
                        stable_id("processing", sample_id, "1"),
                        sample_id,
                        processing_raw,
                        processing_temperature,
                        processing_raw,
                    ],
                )

            connection.execute(
                """
                INSERT INTO alloy.experimental_phase_observations (
                    observation_id,
                    sample_id,
                    phase_id,
                    raw_phase_label,
                    phase_fraction,
                    characterization_method,
                    observation_temperature_K,
                    source_locator
                )
                VALUES (?, ?, NULL, ?, NULL, NULL, NULL, ?)
                """,
                [
                    stable_id("observation", sample_id, phases_raw),
                    sample_id,
                    phases_raw,
                    locator,
                ],
            )

            normalized_tmisc = 300.0 if predicted_tmisc == 0 else predicted_tmisc
            run_id = stable_id(
                "run",
                source_id,
                str(source_row_number),
                "validation_prediction",
            )
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
                VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL)
                """,
                [
                    run_id,
                    MODEL_ID,
                    composition,
                    source_id,
                    json.dumps(
                        {
                            "source_context": "experimental_validation",
                            "source_row_number": source_row_number,
                        },
                        sort_keys=True,
                    ),
                ],
            )
            connection.execute(
                """
                INSERT INTO alloy.miscibility_predictions (
                    prediction_id,
                    run_id,
                    composition_id,
                    reported_miscibility_temperature_K,
                    miscibility_temperature_K,
                    normalization_rule,
                    legacy_melting_temperature_K,
                    source_row_number,
                    quality_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'authoritative_validation')
                """,
                [
                    stable_id("prediction", run_id),
                    run_id,
                    composition,
                    predicted_tmisc,
                    normalized_tmisc,
                    (
                        "zero_to_room_temperature"
                        if predicted_tmisc == 0
                        else "none"
                    ),
                    source_row_number,
                ],
            )

    report = _counts(
        connection,
        source_id=source_id,
        already_ingested=False,
    )
    if report.staged_rows != len(rows) or report.substantive_rows != 109:
        raise RuntimeError(f"Unexpected validation ingestion counts: {report}")
    return report

