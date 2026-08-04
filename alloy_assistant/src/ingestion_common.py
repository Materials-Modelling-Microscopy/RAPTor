"""Shared primitives for transactional, source-aware ingestion."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT
from .normalization import (
    ELEMENTS,
    canonical_formula,
    canonical_system_name,
    composition_id,
    sha256_file,
    stable_id,
    system_id,
)


STAGING_SCHEMA_PATH = (
    ALLOY_ASSISTANT_ROOT / "catalog" / "staging_schema.sql"
)


@contextmanager
def transaction(connection: DuckDBPyConnection) -> Iterator[None]:
    connection.execute("BEGIN TRANSACTION")
    try:
        yield
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def ensure_staging_schema(connection: DuckDBPyConnection) -> None:
    connection.execute(STAGING_SCHEMA_PATH.read_text(encoding="utf-8"))


def source_identity(path: Path) -> tuple[str, str]:
    checksum = sha256_file(path)
    return stable_id("source", checksum), checksum


def source_exists(
    connection: DuckDBPyConnection,
    *,
    sha256: str,
) -> str | None:
    row = connection.execute(
        "SELECT source_id FROM alloy.sources WHERE sha256 = ?",
        [sha256],
    ).fetchone()
    return None if row is None else str(row[0])


def register_source(
    connection: DuckDBPyConnection,
    *,
    path: Path,
    source_id: str,
    sha256: str,
    source_class: str,
    title: str,
    authority_status: str,
    confidentiality: str = "internal",
    version_label: str = "legacy-unknown",
    notes: str | None = None,
) -> None:
    resolved = path.expanduser().resolve()
    try:
        stored_path = str(resolved.relative_to(ALLOY_ASSISTANT_ROOT))
    except ValueError:
        stored_path = str(resolved)

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        [
            source_id,
            source_class,
            title,
            stored_path,
            sha256,
            version_label,
            confidentiality,
            authority_status,
            notes,
        ],
    )


def upsert_elements(
    connection: DuckDBPyConnection,
    elements: tuple[str, ...],
) -> None:
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
            (element, ELEMENTS[element][0], ELEMENTS[element][1])
            for element in elements
        ],
    )


def upsert_system(
    connection: DuckDBPyConnection,
    elements: tuple[str, ...],
) -> str:
    identifier = system_id(elements)
    upsert_elements(connection, elements)
    connection.execute(
        """
        INSERT INTO alloy.alloy_systems (
            system_id,
            canonical_name,
            n_components
        )
        VALUES (?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [identifier, canonical_system_name(elements), len(elements)],
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
        [(identifier, element) for element in elements],
    )
    return identifier


def upsert_composition(
    connection: DuckDBPyConnection,
    *,
    fractions: dict[str, float],
    original_formula: str,
    source_id: str,
    source_locator: str,
    is_equimolar: bool,
) -> str:
    elements = tuple(sorted(fractions))
    system_identifier = upsert_system(connection, elements)
    identifier = composition_id(fractions)

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
        VALUES (?, ?, ?, ?, 'atomic_fraction', ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [
            identifier,
            system_identifier,
            canonical_formula(fractions),
            original_formula,
            is_equimolar,
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
        VALUES (?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        [
            (identifier, element, fraction)
            for element, fraction in fractions.items()
        ],
    )
    return identifier


def upsert_model(
    connection: DuckDBPyConnection,
    *,
    model_id: str,
    model_name: str,
    description: str,
    model_version: str = "legacy-unknown",
) -> None:
    connection.execute(
        """
        INSERT INTO alloy.models (
            model_id,
            model_name,
            model_version,
            description,
            code_source_id
        )
        VALUES (?, ?, ?, ?, NULL)
        ON CONFLICT DO NOTHING
        """,
        [model_id, model_name, model_version, description],
    )

