"""Create the persistent Alloy Assistant DuckDB database."""

from __future__ import annotations

import argparse
from pathlib import Path

from .database import DEFAULT_DATABASE_PATH, connect, initialize_schema
from .validate_schema import format_validation, inspect_schema


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize the Alloy Assistant DuckDB database.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path for the persistent DuckDB database.",
    )
    return parser.parse_args()


def initialize_database(database_path: Path) -> bool:
    """Initialize a new database or validate an existing database.

    Returns ``True`` when a new database was created and ``False`` when an
    existing valid database was left unchanged.
    """
    resolved_path = database_path.expanduser().resolve()

    if resolved_path.exists():
        with connect(resolved_path, read_only=True) as connection:
            result = inspect_schema(connection)
        if not result.is_valid:
            raise RuntimeError(
                "Database already exists but does not match the expected "
                f"schema:\n{format_validation(result)}"
            )
        print(f"Database already initialized: {resolved_path}")
        print(format_validation(result))
        return False

    with connect(resolved_path) as connection:
        initialize_schema(connection)
        result = inspect_schema(connection)
        if not result.is_valid:
            raise RuntimeError(
                "Schema initialization did not produce the expected objects:\n"
                f"{format_validation(result)}"
            )

    print(f"Database initialized: {resolved_path}")
    print(format_validation(result))
    return True


def main() -> int:
    """Initialize the configured persistent database."""
    args = parse_args()
    initialize_database(args.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

