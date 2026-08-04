"""Ingest the binary equimolar CSV through staging into curated tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT, DEFAULT_DATABASE_PATH, connect


DEFAULT_SOURCE_PATH = (
    ALLOY_ASSISTANT_ROOT
    / "data"
    / "inbox"
    / "computational_results"
    / "binary_equimolar_data.csv"
)
STAGING_SCHEMA_PATH = (
    ALLOY_ASSISTANT_ROOT / "catalog" / "staging_schema.sql"
)

EXPECTED_COLUMNS = (
    "",
    "Name",
    "T_melt (K)",
    "T_misc (K)",
    "Hmix",
    "decomp_product_atT_melt",
    "decomp_product_atT_misc",
    "miscibility",
    "expt.",
)

ELEMENTS = {
    "Cr": (24, "Chromium"),
    "Hf": (72, "Hafnium"),
    "Mo": (42, "Molybdenum"),
    "Nb": (41, "Niobium"),
    "Ta": (73, "Tantalum"),
    "Ti": (22, "Titanium"),
    "V": (23, "Vanadium"),
    "W": (74, "Tungsten"),
    "Zr": (40, "Zirconium"),
}

MODEL_ID = "model_binary_equimolar_legacy"


@dataclass(frozen=True)
class BinaryEquimolarRow:
    """One validated source row before database insertion."""

    source_row_number: int
    source_index: int
    alloy_name: str
    elements: tuple[str, str]
    melting_temperature_K: float
    reported_miscibility_temperature_K: float
    hmix_eV_atom: float
    decomposition_at_melting_raw: str
    decomposition_at_miscibility_raw: str
    legacy_miscibility_ratio: float
    experimental_temperature_K_raw: float | None

    @property
    def canonical_system_name(self) -> str:
        return "-".join(self.elements)

    @property
    def normalized_miscibility_temperature_K(self) -> float:
        if self.reported_miscibility_temperature_K == 0:
            return 300.0
        return self.reported_miscibility_temperature_K

    @property
    def normalization_rule(self) -> str:
        if self.reported_miscibility_temperature_K == 0:
            return "zero_to_room_temperature"
        return "none"


@dataclass(frozen=True)
class IngestionReport:
    """Counts proving what one source contributed to the database."""

    source_id: str
    source_sha256: str
    already_ingested: bool
    staged_rows: int
    elements: int
    alloy_systems: int
    compositions: int
    composition_components: int
    pairwise_interactions: int
    calculation_runs: int
    miscibility_predictions: int
    normalized_room_temperature_rows: int


def _parse_required_float(value: str | None, *, field: str, row: int) -> float:
    if value is None or not value.strip():
        raise ValueError(f"Row {row}: {field} is required")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"Row {row}: {field} must be finite")
    return parsed


def _parse_optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_elements(alloy_name: str, *, row: int) -> tuple[str, str]:
    parts = tuple(sorted(part.strip() for part in alloy_name.split("-")))
    if len(parts) != 2 or any(not part for part in parts):
        raise ValueError(
            f"Row {row}: expected a binary name like Cr-Hf, got {alloy_name!r}"
        )
    unknown = [element for element in parts if element not in ELEMENTS]
    if unknown:
        raise ValueError(f"Row {row}: unknown elements: {unknown}")
    return parts


def read_and_validate_source(source_path: Path) -> list[BinaryEquimolarRow]:
    """Parse the CSV without changing it and enforce source-level invariants."""
    if not source_path.is_file():
        raise FileNotFoundError(f"Source CSV does not exist: {source_path}")

    parsed_rows: list[BinaryEquimolarRow] = []
    seen_systems: set[tuple[str, str]] = set()

    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_columns = tuple(reader.fieldnames or ())
        if actual_columns != EXPECTED_COLUMNS:
            raise ValueError(
                "Unexpected CSV columns.\n"
                f"Expected: {EXPECTED_COLUMNS}\n"
                f"Observed: {actual_columns}"
            )

        for source_row_number, raw in enumerate(reader, start=2):
            alloy_name = (raw["Name"] or "").strip()
            elements = _parse_elements(alloy_name, row=source_row_number)
            if elements in seen_systems:
                raise ValueError(
                    f"Row {source_row_number}: duplicate system {elements}"
                )
            seen_systems.add(elements)

            melting_temperature = _parse_required_float(
                raw["T_melt (K)"],
                field="T_melt (K)",
                row=source_row_number,
            )
            reported_miscibility_temperature = _parse_required_float(
                raw["T_misc (K)"],
                field="T_misc (K)",
                row=source_row_number,
            )
            hmix = _parse_required_float(
                raw["Hmix"],
                field="Hmix",
                row=source_row_number,
            )
            legacy_ratio = _parse_required_float(
                raw["miscibility"],
                field="miscibility",
                row=source_row_number,
            )

            if melting_temperature <= 0:
                raise ValueError(
                    f"Row {source_row_number}: melting temperature must be > 0"
                )
            if reported_miscibility_temperature < 0:
                raise ValueError(
                    f"Row {source_row_number}: miscibility temperature must be >= 0"
                )
            if reported_miscibility_temperature > 0:
                calculated_ratio = (
                    reported_miscibility_temperature / melting_temperature
                )
                if not math.isclose(
                    calculated_ratio,
                    legacy_ratio,
                    rel_tol=1e-8,
                    abs_tol=1e-8,
                ):
                    raise ValueError(
                        f"Row {source_row_number}: stored miscibility ratio "
                        f"{legacy_ratio} does not match T_misc/T_melt "
                        f"({calculated_ratio})"
                    )

            parsed_rows.append(
                BinaryEquimolarRow(
                    source_row_number=source_row_number,
                    source_index=int(raw[""]),
                    alloy_name=alloy_name,
                    elements=elements,
                    melting_temperature_K=melting_temperature,
                    reported_miscibility_temperature_K=(
                        reported_miscibility_temperature
                    ),
                    hmix_eV_atom=hmix,
                    decomposition_at_melting_raw=(
                        raw["decomp_product_atT_melt"] or ""
                    ),
                    decomposition_at_miscibility_raw=(
                        raw["decomp_product_atT_misc"] or ""
                    ),
                    legacy_miscibility_ratio=legacy_ratio,
                    experimental_temperature_K_raw=_parse_optional_float(
                        raw["expt."]
                    ),
                )
            )

    if not parsed_rows:
        raise ValueError("Source CSV contains no data rows")

    observed_elements = {element for row in parsed_rows for element in row.elements}
    expected_pair_count = len(observed_elements) * (len(observed_elements) - 1) // 2
    if len(parsed_rows) != expected_pair_count:
        raise ValueError(
            "Binary coverage is incomplete: "
            f"found {len(parsed_rows)} pairs for {len(observed_elements)} "
            f"elements; expected {expected_pair_count}"
        )

    return parsed_rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    suffix = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}_{suffix}"


def _system_id(elements: tuple[str, str]) -> str:
    return "system_" + "_".join(element.lower() for element in elements)


def _composition_id(elements: tuple[str, str]) -> str:
    return "composition_" + "_".join(
        f"{element.lower()}_0p5" for element in elements
    )


def _ensure_staging_schema(connection: DuckDBPyConnection) -> None:
    staging_sql = STAGING_SCHEMA_PATH.read_text(encoding="utf-8")
    connection.execute(staging_sql)


def _source_exists(connection: DuckDBPyConnection, sha256: str) -> str | None:
    row = connection.execute(
        "SELECT source_id FROM alloy.sources WHERE sha256 = ?",
        [sha256],
    ).fetchone()
    return None if row is None else str(row[0])


def _report(
    connection: DuckDBPyConnection,
    *,
    source_id: str,
    source_sha256: str,
    already_ingested: bool,
) -> IngestionReport:
    scalar_queries = {
        "staged_rows": """
            SELECT count(*)
            FROM staging.binary_equimolar_data_raw
            WHERE source_id = ?
        """,
        "elements": """
            SELECT count(DISTINCT cc.element_symbol)
            FROM alloy.composition_components AS cc
            JOIN alloy.compositions AS c USING (composition_id)
            WHERE c.source_id = ?
        """,
        "alloy_systems": """
            SELECT count(DISTINCT c.system_id)
            FROM alloy.compositions AS c
            WHERE c.source_id = ?
        """,
        "compositions": """
            SELECT count(*)
            FROM alloy.compositions
            WHERE source_id = ?
        """,
        "composition_components": """
            SELECT count(*)
            FROM alloy.composition_components AS cc
            JOIN alloy.compositions AS c USING (composition_id)
            WHERE c.source_id = ?
        """,
        "pairwise_interactions": """
            SELECT count(*)
            FROM alloy.pairwise_interactions
            WHERE source_id = ?
        """,
        "calculation_runs": """
            SELECT count(*)
            FROM alloy.calculation_runs
            WHERE result_source_id = ?
        """,
        "miscibility_predictions": """
            SELECT count(*)
            FROM alloy.miscibility_predictions AS mp
            JOIN alloy.calculation_runs AS cr USING (run_id)
            WHERE cr.result_source_id = ?
        """,
        "normalized_room_temperature_rows": """
            SELECT count(*)
            FROM alloy.miscibility_predictions AS mp
            JOIN alloy.calculation_runs AS cr USING (run_id)
            WHERE cr.result_source_id = ?
              AND mp.normalization_rule = 'zero_to_room_temperature'
        """,
    }
    counts = {
        name: int(connection.execute(query, [source_id]).fetchone()[0])
        for name, query in scalar_queries.items()
    }
    return IngestionReport(
        source_id=source_id,
        source_sha256=source_sha256,
        already_ingested=already_ingested,
        **counts,
    )


def _validate_curated_records(
    connection: DuckDBPyConnection,
    *,
    source_id: str,
    expected_rows: int,
) -> None:
    report = _report(
        connection,
        source_id=source_id,
        source_sha256="validation-only",
        already_ingested=False,
    )
    expected_counts = {
        "staged_rows": expected_rows,
        "alloy_systems": expected_rows,
        "compositions": expected_rows,
        "composition_components": expected_rows * 2,
        "pairwise_interactions": expected_rows,
        "calculation_runs": expected_rows,
        "miscibility_predictions": expected_rows,
    }
    for field, expected in expected_counts.items():
        observed = getattr(report, field)
        if observed != expected:
            raise RuntimeError(
                f"Post-ingestion validation failed for {field}: "
                f"expected {expected}, observed {observed}"
            )

    invalid_compositions = connection.execute(
        """
        SELECT c.composition_id, sum(cc.fraction) AS fraction_sum
        FROM alloy.compositions AS c
        JOIN alloy.composition_components AS cc USING (composition_id)
        WHERE c.source_id = ?
        GROUP BY c.composition_id
        HAVING abs(sum(cc.fraction) - 1.0) > 1e-12
        """,
        [source_id],
    ).fetchall()
    if invalid_compositions:
        raise RuntimeError(
            "Composition fractions do not sum to one: "
            f"{invalid_compositions}"
        )


def ingest_binary_equimolar(
    connection: DuckDBPyConnection,
    source_path: Path = DEFAULT_SOURCE_PATH,
) -> IngestionReport:
    """Stage, normalize, and curate the binary equimolar dataset atomically."""
    resolved_source = source_path.expanduser().resolve()
    rows = read_and_validate_source(resolved_source)
    source_sha256 = _sha256(resolved_source)
    source_id = _stable_id("source", source_sha256)

    _ensure_staging_schema(connection)
    existing_source_id = _source_exists(connection, source_sha256)
    if existing_source_id is not None:
        return _report(
            connection,
            source_id=existing_source_id,
            source_sha256=source_sha256,
            already_ingested=True,
        )

    relative_source_path = resolved_source.relative_to(ALLOY_ASSISTANT_ROOT)

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            """
            INSERT INTO alloy.sources (
                source_id,
                source_class,
                title,
                original_path,
                sha256,
                version_label,
                confidentiality,
                authority_status,
                citation,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                source_id,
                "computational_dataset",
                "Binary equimolar miscibility and pair interactions",
                str(relative_source_path),
                source_sha256,
                "legacy-unknown",
                "internal",
                "authoritative_curated",
                None,
                (
                    "Original CSV preserved in inbox. Pair Hmix is at 0 K in "
                    "eV/atom. Reported T_misc=0 K is curated as 300 K."
                ),
            ],
        )

        connection.executemany(
            """
            INSERT INTO alloy.elements (
                element_symbol,
                atomic_number,
                element_name
            )
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            [
                (symbol, atomic_number, name)
                for symbol, (atomic_number, name) in ELEMENTS.items()
            ],
        )

        connection.execute(
            """
            INSERT INTO alloy.models (
                model_id,
                model_name,
                model_version,
                description,
                code_source_id
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            [
                MODEL_ID,
                "Legacy binary equimolar workflow",
                "legacy-unknown",
                (
                    "Pair mixing enthalpy at 0 K from DFT with legacy "
                    "miscibility calculations."
                ),
                None,
            ],
        )

        for row in rows:
            system_id = _system_id(row.elements)
            composition_id = _composition_id(row.elements)
            run_id = _stable_id("run", source_id, row.canonical_system_name)
            interaction_id = _stable_id(
                "interaction",
                MODEL_ID,
                row.elements[0],
                row.elements[1],
                source_id,
            )
            prediction_id = _stable_id("prediction", run_id)
            source_locator = f"csv-row:{row.source_row_number}"

            connection.execute(
                """
                INSERT INTO staging.binary_equimolar_data_raw
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source_id,
                    row.source_row_number,
                    row.source_index,
                    row.alloy_name,
                    row.melting_temperature_K,
                    row.reported_miscibility_temperature_K,
                    row.hmix_eV_atom,
                    row.decomposition_at_melting_raw,
                    row.decomposition_at_miscibility_raw,
                    row.legacy_miscibility_ratio,
                    row.experimental_temperature_K_raw,
                ],
            )

            connection.execute(
                """
                INSERT INTO alloy.alloy_systems (
                    system_id,
                    canonical_name,
                    n_components
                )
                VALUES (?, ?, 2)
                ON CONFLICT DO NOTHING
                """,
                [system_id, row.canonical_system_name],
            )

            connection.executemany(
                """
                INSERT INTO alloy.alloy_system_elements (
                    system_id,
                    element_symbol
                )
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                [(system_id, element) for element in row.elements],
            )

            canonical_formula = "-".join(
                f"{element}0.5" for element in row.elements
            )
            connection.execute(
                """
                INSERT INTO alloy.compositions (
                    composition_id,
                    system_id,
                    canonical_formula,
                    original_formula,
                    basis,
                    is_equimolar,
                    source_id,
                    source_locator
                )
                VALUES (?, ?, ?, ?, 'atomic_fraction', TRUE, ?, ?)
                """,
                [
                    composition_id,
                    system_id,
                    canonical_formula,
                    row.alloy_name,
                    source_id,
                    source_locator,
                ],
            )

            connection.executemany(
                """
                INSERT INTO alloy.composition_components (
                    composition_id,
                    element_symbol,
                    fraction
                )
                VALUES (?, ?, 0.5)
                """,
                [
                    (composition_id, row.elements[0]),
                    (composition_id, row.elements[1]),
                ],
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
                    composition_id,
                    source_id,
                    json.dumps(
                        {
                            "composition": "equimolar",
                            "source_format": "legacy_csv",
                        },
                        sort_keys=True,
                    ),
                ],
            )

            connection.execute(
                """
                INSERT INTO alloy.pairwise_interactions (
                    interaction_id,
                    model_id,
                    element_a,
                    element_b,
                    interaction_type,
                    value_eV_atom,
                    source_id
                )
                VALUES (?, ?, ?, ?, 'mixing_enthalpy_0K', ?, ?)
                """,
                [
                    interaction_id,
                    MODEL_ID,
                    row.elements[0],
                    row.elements[1],
                    row.hmix_eV_atom,
                    source_id,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    prediction_id,
                    run_id,
                    composition_id,
                    row.reported_miscibility_temperature_K,
                    row.normalized_miscibility_temperature_K,
                    row.normalization_rule,
                    row.melting_temperature_K,
                    row.source_row_number,
                    (
                        "normalized_room_temperature"
                        if row.normalization_rule == "zero_to_room_temperature"
                        else "validated"
                    ),
                ],
            )

        _validate_curated_records(
            connection,
            source_id=source_id,
            expected_rows=len(rows),
        )
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")

    return _report(
        connection,
        source_id=source_id,
        source_sha256=source_sha256,
        already_ingested=False,
    )


def format_report(report: IngestionReport) -> str:
    """Format an auditable ingestion summary."""
    status = "already ingested" if report.already_ingested else "ingested"
    return "\n".join(
        [
            f"Status: {status}",
            f"Source ID: {report.source_id}",
            f"SHA-256: {report.source_sha256}",
            f"Staging rows: {report.staged_rows}",
            f"Elements: {report.elements}",
            f"Alloy systems: {report.alloy_systems}",
            f"Compositions: {report.compositions}",
            f"Composition components: {report.composition_components}",
            f"Pair interactions: {report.pairwise_interactions}",
            f"Calculation runs: {report.calculation_runs}",
            f"Miscibility predictions: {report.miscibility_predictions}",
            (
                "T_misc rows normalized from 0 K to 300 K: "
                f"{report.normalized_room_temperature_rows}"
            ),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest binary equimolar data into Alloy Assistant.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the initialized DuckDB database.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help="Path to binary_equimolar_data.csv.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the source CSV without changing a database.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.source.expanduser().resolve()

    if args.dry_run:
        rows = read_and_validate_source(source_path)
        normalized = sum(
            row.normalization_rule == "zero_to_room_temperature"
            for row in rows
        )
        print(f"Source valid: {source_path}")
        print(f"Rows: {len(rows)}")
        print(f"T_misc rows requiring 0 K -> 300 K normalization: {normalized}")
        return 0

    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(
            "Database does not exist. Initialize it first with: "
            "python -m alloy_assistant.src.initialize_database"
        )

    with connect(database_path) as connection:
        report = ingest_binary_equimolar(connection, source_path)
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
