"""Register all inbox TDB files as versioned thermodynamic inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT
from .ingestion_common import (
    ensure_staging_schema,
    register_source,
    source_exists,
    source_identity,
    transaction,
    upsert_system,
)
from .normalization import canonical_elements, stable_id


TDB_ROOT = (
    ALLOY_ASSISTANT_ROOT / "data" / "inbox" / "alloy_databases" / "tdbs"
)


@dataclass(frozen=True)
class TdbRegistryReport:
    files_discovered: int
    files_registered: int
    files_already_registered: int
    systems_registered: int


def _keyword_count(text: str, keyword: str) -> int:
    return len(
        re.findall(
            rf"(?mi)^\s*{re.escape(keyword)}\b",
            text,
        )
    )


def ingest_tdb_registry(
    connection: DuckDBPyConnection,
) -> TdbRegistryReport:
    ensure_staging_schema(connection)
    paths = sorted(TDB_ROOT.glob("*.tdb"))
    if not paths:
        raise FileNotFoundError(f"No TDB files found in {TDB_ROOT}")

    prepared = []
    existing = 0
    for path in paths:
        source_id, checksum = source_identity(path)
        if source_exists(connection, sha256=checksum) is not None:
            existing += 1
            continue
        elements = canonical_elements(tuple(path.stem.split("-")))
        text = path.read_text(encoding="utf-8", errors="replace")
        prepared.append(
            {
                "path": path,
                "source_id": source_id,
                "checksum": checksum,
                "elements": elements,
                "phase_count": _keyword_count(text, "PHASE"),
                "parameter_count": _keyword_count(text, "PARAMETER"),
            }
        )

    with transaction(connection):
        for item in prepared:
            elements = item["elements"]
            path = item["path"]
            register_source(
                connection,
                path=path,
                source_id=item["source_id"],
                sha256=item["checksum"],
                source_class="thermodynamic_database",
                title=f"TDB for {'-'.join(elements)}",
                authority_status="supporting",
                notes=(
                    "Registered as a versioned TDB calculation input. "
                    "Detailed functions and parameters are not yet decomposed."
                ),
            )
            system_identifier = upsert_system(connection, elements)
            tdb_id = stable_id("tdb", item["source_id"])
            connection.execute(
                """
                INSERT INTO staging.tdb_registry_raw
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    item["source_id"],
                    path.name,
                    "-".join(elements),
                    len(elements),
                    item["phase_count"],
                    item["parameter_count"],
                ],
            )
            connection.execute(
                """
                INSERT INTO alloy.thermodynamic_databases (
                    tdb_id,
                    source_id,
                    system_id,
                    software_compatibility,
                    parameter_count,
                    phase_count
                )
                VALUES (?, ?, ?, 'TDB-format', ?, ?)
                """,
                [
                    tdb_id,
                    item["source_id"],
                    system_identifier,
                    item["parameter_count"],
                    item["phase_count"],
                ],
            )

    systems = int(
        connection.execute(
            """
            SELECT count(DISTINCT system_id)
            FROM alloy.thermodynamic_databases
            """
        ).fetchone()[0]
    )
    return TdbRegistryReport(
        files_discovered=len(paths),
        files_registered=len(prepared),
        files_already_registered=existing,
        systems_registered=systems,
    )

