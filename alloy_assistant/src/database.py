"""DuckDB connection and schema utilities.

This module is the single place where application code opens DuckDB
connections. Centralizing connection behavior prevents scripts from quietly
using different database paths or connection settings.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
from duckdb import DuckDBPyConnection


ALLOY_ASSISTANT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ALLOY_ASSISTANT_ROOT / "catalog" / "schema.sql"
DEFAULT_DATABASE_PATH = (
    ALLOY_ASSISTANT_ROOT / "data" / "generated" / "alloy_assistant.duckdb"
)


def read_schema_sql(schema_path: Path = SCHEMA_PATH) -> str:
    """Read the version-controlled schema definition."""
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file does not exist: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8").strip()
    if not schema_sql:
        raise ValueError(f"Schema file is empty: {schema_path}")
    return schema_sql


@contextmanager
def connect(
    database: str | Path = ":memory:",
    *,
    read_only: bool = False,
) -> Iterator[DuckDBPyConnection]:
    """Open and reliably close a DuckDB connection.

    Parent directories are created only for a writable, file-backed database.
    The special ``:memory:`` database never writes to disk.
    """
    database_name = str(database)

    if database_name != ":memory:" and not read_only:
        Path(database_name).expanduser().resolve().parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    connection = duckdb.connect(
        database=database_name,
        read_only=read_only,
    )
    try:
        yield connection
    finally:
        connection.close()


def initialize_schema(
    connection: DuckDBPyConnection,
    *,
    schema_path: Path = SCHEMA_PATH,
) -> None:
    """Create all schema objects as one transaction.

    A transaction makes schema initialization atomic: either every statement
    succeeds, or DuckDB rolls the changes back.
    """
    schema_sql = read_schema_sql(schema_path)

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(schema_sql)
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")

