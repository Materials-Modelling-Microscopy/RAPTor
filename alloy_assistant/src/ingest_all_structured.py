"""Run every structured-data ingestion step in dependency order."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import DEFAULT_DATABASE_PATH, connect
from .ingest_binary_equimolar import ingest_binary_equimolar
from .ingest_equimolar_series import ingest_equimolar_series
from .ingest_experimental_validation import (
    ingest_experimental_validation,
)
from .ingest_pmr_series import ingest_pmr_series
from .ingest_tdb_registry import ingest_tdb_registry
from .validate_schema import format_validation, inspect_schema


def ingest_all_structured(
    connection: DuckDBPyConnection,
) -> dict[str, object]:
    """Ingest all reviewed structured sources.

    The binary dataset runs first because its pairwise enthalpies are used to
    validate the higher-order equimolar exports.
    """
    reports = {
        "binary_equimolar": asdict(ingest_binary_equimolar(connection)),
        "higher_order_equimolar": asdict(
            ingest_equimolar_series(connection)
        ),
        "pmr": asdict(ingest_pmr_series(connection)),
        "experimental_validation": asdict(
            ingest_experimental_validation(connection)
        ),
        "tdb_registry": asdict(ingest_tdb_registry(connection)),
    }
    reports["database_totals"] = _database_totals(connection)
    return reports


def _database_totals(
    connection: DuckDBPyConnection,
) -> dict[str, int]:
    tables = (
        "sources",
        "elements",
        "alloy_systems",
        "compositions",
        "pairwise_interactions",
        "calculation_runs",
        "miscibility_predictions",
        "pmr_predictions",
        "predicted_phase_fractions",
        "experimental_samples",
        "processing_events",
        "experimental_phase_observations",
        "thermodynamic_databases",
    )
    return {
        table: int(
            connection.execute(
                f"SELECT count(*) FROM alloy.{table}"
            ).fetchone()[0]
        )
        for table in tables
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest all reviewed Alloy Assistant structured data.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to an initialized Alloy Assistant DuckDB database.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Database is not initialized: {database_path}\n"
            "Run python -m alloy_assistant.src.initialize_database first."
        )

    with connect(database_path) as connection:
        validation = inspect_schema(connection)
        if not validation.is_valid:
            raise RuntimeError(format_validation(validation))
        report = ingest_all_structured(connection)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
