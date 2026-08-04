"""Ingest ternary, quaternary, and quinary equimolar predictions."""

from __future__ import annotations

import ast
import csv
import itertools
import json
import math
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
    upsert_composition,
    upsert_model,
)
from .normalization import (
    canonical_elements,
    equimolar_fractions,
    stable_id,
)


COMPUTATIONAL_ROOT = (
    ALLOY_ASSISTANT_ROOT / "data" / "inbox" / "computational_results"
)

EQUIMOLAR_FILES = {
    3: COMPUTATIONAL_ROOT / "ternary_equimolar_data.csv",
    4: COMPUTATIONAL_ROOT / "quaternary_equimolar_data.csv",
    5: COMPUTATIONAL_ROOT / "quinary_equimolar_data.csv",
}

MODEL_ID = "model_equimolar_miscibility_legacy"
PAIR_MODEL_ID = "model_binary_equimolar_legacy"


@dataclass(frozen=True)
class EquimolarIngestionReport:
    files_ingested: int
    files_already_ingested: int
    staged_rows: int
    miscibility_predictions: int
    phase_fraction_rows: int


def _phase_dictionary(text: str) -> list[tuple[str, float]]:
    """Safely parse the limited dictionary syntax used by the CSV exports."""
    node = ast.parse(text, mode="eval").body
    if not isinstance(node, ast.Dict):
        raise ValueError(f"Expected a dictionary, got: {text!r}")

    parsed: list[tuple[str, float]] = []
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(
            key_node.value,
            str,
        ):
            raise ValueError(f"Unsupported phase key in: {text!r}")
        phase = key_node.value.strip()
        if not phase:
            continue

        if isinstance(value_node, ast.Constant) and isinstance(
            value_node.value,
            (int, float),
        ):
            value = float(value_node.value)
        elif (
            isinstance(value_node, ast.UnaryOp)
            and isinstance(value_node.op, ast.USub)
            and isinstance(value_node.operand, ast.Constant)
        ):
            value = -float(value_node.operand.value)
        elif isinstance(value_node, ast.Name) and value_node.id == "nan":
            continue
        else:
            raise ValueError(f"Unsupported phase fraction in: {text!r}")

        if not math.isfinite(value) or value < 0 or value > 1:
            raise ValueError(f"Invalid phase fraction {value} in: {text!r}")
        parsed.append((phase, value))
    return parsed


def _phase_family(raw_phase: str) -> str:
    if raw_phase.startswith("BCC"):
        return "BCC"
    if raw_phase.startswith("HCP"):
        return "HCP"
    return "INTERMETALLIC"


def _insert_phase_fraction_rows(
    connection: DuckDBPyConnection,
    *,
    run_id: str,
    composition_id: str,
    temperature_K: float,
    phase_text: str,
    source_locator: str,
    state_label: str,
) -> int:
    count = 0
    for raw_phase, fraction in _phase_dictionary(phase_text):
        phase_id = stable_id("phase", raw_phase)
        connection.execute(
            """
            INSERT INTO alloy.phases (
                phase_id,
                canonical_name,
                phase_family,
                notes
            )
            VALUES (?, ?, ?, NULL)
            ON CONFLICT DO NOTHING
            """,
            [phase_id, raw_phase, _phase_family(raw_phase)],
        )
        connection.execute(
            """
            INSERT INTO alloy.predicted_phase_fractions (
                phase_fraction_id,
                run_id,
                composition_id,
                temperature_K,
                phase_id,
                raw_phase_label,
                phase_fraction,
                source_locator
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                stable_id(
                    "phase_fraction",
                    run_id,
                    state_label,
                    raw_phase,
                ),
                run_id,
                composition_id,
                temperature_K,
                phase_id,
                raw_phase,
                fraction,
                f"{source_locator};state:{state_label}",
            ],
        )
        count += 1
    return count


def _pair_values_for_row(
    row: dict[str, str],
    *,
    elements: tuple[str, ...],
) -> list[tuple[tuple[str, str], str, float]]:
    pair_columns = [
        column
        for column in row
        if column.startswith("Hmix") and column != "Hmix"
    ]
    pairs = list(itertools.combinations(elements, 2))
    if len(pair_columns) != len(pairs):
        raise ValueError(
            f"Expected {len(pairs)} pair columns for {elements}, "
            f"found {pair_columns}"
        )
    return [
        (pair, column, float(row[column]))
        for pair, column in zip(pairs, pair_columns)
    ]


def _validate_pair_values(
    connection: DuckDBPyConnection,
    pair_values: list[tuple[tuple[str, str], str, float]],
) -> None:
    for (element_a, element_b), _, source_value in pair_values:
        record = connection.execute(
            """
            SELECT value_eV_atom
            FROM alloy.pairwise_interactions
            WHERE model_id = ?
              AND element_a = ?
              AND element_b = ?
            """,
            [PAIR_MODEL_ID, element_a, element_b],
        ).fetchone()
        if record is None:
            raise RuntimeError(
                f"Missing curated pair interaction for {element_a}-{element_b}"
            )
        if not math.isclose(
            float(record[0]),
            source_value,
            rel_tol=0,
            abs_tol=1e-10,
        ):
            raise ValueError(
                f"Pair interaction mismatch for {element_a}-{element_b}: "
                f"binary={record[0]}, multicomponent={source_value}"
            )


def _ingest_file(
    connection: DuckDBPyConnection,
    *,
    n_components: int,
    path: Path,
) -> tuple[bool, int, int]:
    source_id, checksum = source_identity(path)
    if source_exists(connection, sha256=checksum):
        return False, 0, 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No rows in {path}")

    staged_count = 0
    phase_count = 0
    with transaction(connection):
        register_source(
            connection,
            path=path,
            source_id=source_id,
            sha256=checksum,
            source_class="computational_dataset",
            title=f"{n_components}-component equimolar miscibility predictions",
            authority_status="authoritative_curated",
            notes=(
                "T_misc=0 K is normalized to 300 K. Positional pair columns "
                "are decoded by canonical lexicographic pair order."
            ),
        )
        upsert_model(
            connection,
            model_id=MODEL_ID,
            model_name="Legacy equimolar miscibility workflow",
            description=(
                "Multicomponent equimolar miscibility and phase predictions "
                "using DFT pair interactions."
            ),
        )

        for source_row_number, row in enumerate(rows, start=2):
            elements = canonical_elements(tuple(row["Name"].split("-")))
            if len(elements) != n_components:
                raise ValueError(
                    f"Row {source_row_number}: expected {n_components} "
                    f"components, found {elements}"
                )
            pair_values = _pair_values_for_row(row, elements=elements)
            _validate_pair_values(connection, pair_values)

            legacy_mean_hmix = float(row["Hmix"])
            calculated_mean = sum(value for _, _, value in pair_values) / len(
                pair_values
            )
            if not math.isclose(
                legacy_mean_hmix,
                calculated_mean,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"Row {source_row_number}: legacy Hmix "
                    f"{legacy_mean_hmix} != mean pair Hmix {calculated_mean}"
                )

            melting_temperature = float(row["T_melt (K)"])
            reported_tmisc = float(row["T_misc (K)"])
            normalized_tmisc = 300.0 if reported_tmisc == 0 else reported_tmisc
            legacy_ratio = float(row["miscibility"])
            if reported_tmisc > 0 and not math.isclose(
                reported_tmisc / melting_temperature,
                legacy_ratio,
                rel_tol=1e-8,
                abs_tol=1e-8,
            ):
                raise ValueError(
                    f"Row {source_row_number}: miscibility ratio mismatch"
                )

            pair_columns_json = json.dumps(
                {
                    column: {
                        "pair": list(pair),
                        "value_eV_atom": value,
                    }
                    for pair, column, value in pair_values
                },
                sort_keys=True,
            )
            connection.execute(
                """
                INSERT INTO staging.equimolar_data_raw
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source_id,
                    source_row_number,
                    int(row[""] if "" in row else row["Unnamed: 0"]),
                    n_components,
                    row["Name"],
                    melting_temperature,
                    reported_tmisc,
                    pair_columns_json,
                    legacy_mean_hmix,
                    row["decomp_product_atT_melt"],
                    row["decomp_product_atT_misc"],
                    legacy_ratio,
                ],
            )

            locator = f"csv-row:{source_row_number}"
            composition = upsert_composition(
                connection,
                fractions=equimolar_fractions(elements),
                original_formula=row["Name"],
                source_id=source_id,
                source_locator=locator,
                is_equimolar=True,
            )
            run_id = stable_id("run", source_id, row["Name"])
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
                            "composition": "equimolar",
                            "n_components": n_components,
                            "source_format": "legacy_csv",
                        },
                        sort_keys=True,
                    ),
                ],
            )
            normalization_rule = (
                "zero_to_room_temperature"
                if reported_tmisc == 0
                else "none"
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'validated')
                """,
                [
                    stable_id("prediction", run_id),
                    run_id,
                    composition,
                    reported_tmisc,
                    normalized_tmisc,
                    normalization_rule,
                    melting_temperature,
                    source_row_number,
                ],
            )
            phase_count += _insert_phase_fraction_rows(
                connection,
                run_id=run_id,
                composition_id=composition,
                temperature_K=melting_temperature,
                phase_text=row["decomp_product_atT_melt"],
                source_locator=locator,
                state_label="melting_temperature",
            )
            phase_count += _insert_phase_fraction_rows(
                connection,
                run_id=run_id,
                composition_id=composition,
                temperature_K=normalized_tmisc,
                phase_text=row["decomp_product_atT_misc"],
                source_locator=locator,
                state_label="miscibility_temperature",
            )
            staged_count += 1

    return True, staged_count, phase_count


def ingest_equimolar_series(
    connection: DuckDBPyConnection,
) -> EquimolarIngestionReport:
    ensure_staging_schema(connection)
    ingested = 0
    existing = 0
    staged = 0
    phase_rows = 0
    for n_components, path in EQUIMOLAR_FILES.items():
        was_ingested, file_rows, file_phases = _ingest_file(
            connection,
            n_components=n_components,
            path=path,
        )
        if was_ingested:
            ingested += 1
            staged += file_rows
            phase_rows += file_phases
        else:
            existing += 1

    prediction_count = int(
        connection.execute(
            """
            SELECT count(*)
            FROM alloy.miscibility_predictions AS mp
            JOIN alloy.calculation_runs AS cr USING (run_id)
            WHERE cr.model_id = ?
            """,
            [MODEL_ID],
        ).fetchone()[0]
    )
    return EquimolarIngestionReport(
        files_ingested=ingested,
        files_already_ingested=existing,
        staged_rows=staged,
        miscibility_predictions=prediction_count,
        phase_fraction_rows=phase_rows,
    )

