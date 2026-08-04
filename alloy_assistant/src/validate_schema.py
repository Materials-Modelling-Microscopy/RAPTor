"""Inspect and validate the Alloy Assistant DuckDB schema."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import DEFAULT_DATABASE_PATH, connect, initialize_schema


EXPECTED_TABLES = frozenset(
    {
        "alloy_system_elements",
        "alloy_systems",
        "calculation_runs",
        "chunk_entities",
        "composition_components",
        "compositions",
        "document_chunks",
        "documents",
        "element_melting_points",
        "elements",
        "experimental_phase_observations",
        "experimental_samples",
        "miscibility_predictions",
        "models",
        "pairwise_interactions",
        "phase_aliases",
        "phases",
        "pmr_predictions",
        "predicted_phase_fractions",
        "processing_events",
        "sources",
        "thermodynamic_databases",
    }
)

EXPECTED_VIEWS = frozenset(
    {
        "composition_weighted_melting_temperatures",
        "miscibility_prediction_metrics",
    }
)

# Generated feature tables can be introduced lazily into an existing database.
# They are part of the current schema for new databases, but their absence does
# not invalidate a database that has not run that pipeline yet.
OPTIONAL_TABLES = frozenset({"chunk_embeddings"})


@dataclass(frozen=True)
class SchemaValidation:
    """Result of comparing observed and expected database objects."""

    tables: frozenset[str]
    views: frozenset[str]
    missing_tables: frozenset[str]
    missing_views: frozenset[str]
    unexpected_tables: frozenset[str]
    unexpected_views: frozenset[str]

    @property
    def is_valid(self) -> bool:
        """Return true when the observed schema matches the expected schema."""
        return not (
            self.missing_tables
            or self.missing_views
            or self.unexpected_tables
            or self.unexpected_views
        )


def inspect_schema(connection: DuckDBPyConnection) -> SchemaValidation:
    """Compare objects in the ``alloy`` schema with the expected contract."""
    rows = connection.execute(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'alloy'
        ORDER BY table_name
        """
    ).fetchall()

    tables = frozenset(name for name, kind in rows if kind == "BASE TABLE")
    views = frozenset(name for name, kind in rows if kind == "VIEW")

    return SchemaValidation(
        tables=tables,
        views=views,
        missing_tables=EXPECTED_TABLES - tables,
        missing_views=EXPECTED_VIEWS - views,
        unexpected_tables=tables - EXPECTED_TABLES - OPTIONAL_TABLES,
        unexpected_views=views - EXPECTED_VIEWS,
    )


def format_validation(result: SchemaValidation) -> str:
    """Create a concise, human-readable validation report."""
    lines = [
        f"Tables: {len(result.tables)}",
        f"Views: {len(result.views)}",
        f"Schema valid: {result.is_valid}",
    ]

    for label, names in (
        ("Missing tables", result.missing_tables),
        ("Missing views", result.missing_views),
        ("Unexpected tables", result.unexpected_tables),
        ("Unexpected views", result.unexpected_views),
    ):
        if names:
            lines.append(f"{label}: {', '.join(sorted(names))}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate Alloy Assistant DuckDB schema objects.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to a persistent DuckDB database.",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Create and validate the schema in memory without writing a file.",
    )
    return parser.parse_args()


def main() -> int:
    """Run schema validation."""
    args = parse_args()

    if args.memory:
        with connect(":memory:") as connection:
            initialize_schema(connection)
            result = inspect_schema(connection)
    else:
        database_path = args.database.expanduser().resolve()
        if not database_path.is_file():
            raise FileNotFoundError(
                "Database does not exist. Initialize it first: "
                f"{database_path}"
            )
        with connect(database_path, read_only=True) as connection:
            result = inspect_schema(connection)

    print(format_validation(result))
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
