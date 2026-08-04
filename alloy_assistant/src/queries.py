"""Reviewed, read-only scientific queries for the Alloy Assistant.

These functions form the numerical tool layer that an eventual RAG agent can
call. Each function accepts an existing DuckDB connection, uses parameterized
SQL for user-supplied values, and returns typed Python objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from duckdb import DuckDBPyConnection

from .normalization import canonical_elements

_LEXICAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
}

MISCIBILITY_RATIO_DEFINITION = (
    "T_misc / T_melting; lower values are more favorable because "
    "miscibility is reached at a smaller fraction of the melting temperature"
)


@dataclass(frozen=True)
class DatabaseSummary:
    """High-level counts for the structured knowledge base."""

    sources: int
    elements: int
    alloy_systems: int
    compositions: int
    pairwise_interactions: int
    calculation_runs: int
    miscibility_predictions: int
    pmr_predictions: int
    predicted_phase_fractions: int
    experimental_samples: int
    thermodynamic_databases: int
    documents: int
    document_chunks: int
    chunk_entities: int


@dataclass(frozen=True)
class BinarySystemSummary:
    """Curated equimolar prediction for one binary system."""

    canonical_name: str
    canonical_formula: str
    hmix_eV_atom: float
    reported_miscibility_temperature_K: float
    miscibility_temperature_K: float
    melting_temperature_K: float
    miscibility_ratio: float
    normalization_rule: str
    quality_flag: str
    model_name: str
    model_version: str
    source_id: str
    miscibility_ratio_definition: str = MISCIBILITY_RATIO_DEFINITION


@dataclass(frozen=True)
class PairwiseInteraction:
    """One binary 0 K mixing enthalpy relevant to a larger alloy system."""

    requested_system: str
    canonical_pair: str
    element_a: str
    element_b: str
    interaction_type: str
    hmix_eV_atom: float
    model_name: str
    model_version: str
    source_id: str


@dataclass(frozen=True)
class SystemOverview:
    """Available structured evidence for one alloy system."""

    canonical_name: str
    n_components: int
    composition_count: int
    miscibility_prediction_count: int
    pmr_prediction_count: int
    predicted_phase_fraction_count: int
    experimental_sample_count: int
    has_thermodynamic_database: bool


@dataclass(frozen=True)
class MiscibilityPrediction:
    """One model result for one exact composition."""

    canonical_name: str
    canonical_formula: str
    original_formula: str | None
    is_equimolar: bool
    reported_miscibility_temperature_K: float
    miscibility_temperature_K: float
    melting_temperature_K: float | None
    miscibility_ratio: float | None
    normalization_rule: str
    quality_flag: str
    model_name: str
    model_version: str
    source_id: str
    source_row_number: int
    miscibility_ratio_definition: str = MISCIBILITY_RATIO_DEFINITION


@dataclass(frozen=True)
class PmrPrediction:
    """Percentage miscible region for one system and temperature."""

    canonical_name: str
    temperature_K: float
    pmr_percent: float
    grid_spacing_atomic_fraction: float
    quality_flag: str
    model_name: str
    model_version: str
    source_id: str
    source_row_number: int


@dataclass(frozen=True)
class PmrCandidate:
    """One system whose representative PMR is near a requested target."""

    canonical_name: str
    n_components: int
    temperature_K: float
    pmr_percent: float
    target_pmr_percent: float
    distance_from_target_percent: float
    grid_spacing_atomic_fraction: float
    quality_flag: str
    model_name: str
    model_version: str
    source_id: str
    source_row_number: int


@dataclass(frozen=True)
class PredictedPhaseFraction:
    """One predicted phase fraction at a recorded state temperature."""

    canonical_name: str
    canonical_formula: str
    temperature_K: float
    phase_name: str
    phase_family: str | None
    phase_fraction: float | None
    model_name: str
    source_id: str
    source_locator: str | None


@dataclass(frozen=True)
class ExperimentalObservation:
    """One source-preserving experimental phase report."""

    canonical_name: str
    canonical_formula: str
    original_formula: str | None
    sample_label: str | None
    processing_route: str | None
    processing_temperature_K: float | None
    raw_phase_label: str
    provenance_status: str
    source_id: str
    source_locator: str | None


@dataclass(frozen=True)
class ThermodynamicDatabaseCoverage:
    """TDB availability and lightweight metadata for one system."""

    canonical_name: str
    has_database: bool
    source_id: str | None
    original_path: str | None
    phase_count: int | None
    parameter_count: int | None
    software_compatibility: str | None


@dataclass(frozen=True)
class DocumentSummary:
    """One ingested document and its retrieval metadata."""

    title: str
    authors: str | None
    publication_year: int | None
    source_class: str
    authority_status: str
    confidentiality: str
    page_count: int
    chunk_count: int
    source_id: str


@dataclass(frozen=True)
class DocumentChunkMatch:
    """One lexical prototype retrieval result."""

    title: str
    page_start: int
    page_end: int
    section_title: str | None
    chunk_text: str
    lexical_score: int
    source_class: str
    authority_status: str
    source_id: str
    chunk_id: str


@dataclass(frozen=True)
class SemanticChunkMatch:
    """One vector-similarity retrieval result."""

    title: str
    page_start: int
    page_end: int
    section_title: str | None
    chunk_text: str
    cosine_similarity: float
    source_class: str
    authority_status: str
    source_id: str
    chunk_id: str


def canonicalize_system(system_name: str) -> str:
    """Normalize a hyphen-separated system name to canonical element order."""
    parts = tuple(
        part.strip().capitalize()
        for part in system_name.split("-")
        if part.strip()
    )
    if len(parts) < 2:
        raise ValueError(
            f"Expected a system like Cr-Hf or Mo-Nb-Ta-W, got {system_name!r}"
        )
    return "-".join(canonical_elements(parts))


def canonicalize_binary_system(system_name: str) -> str:
    """Normalize input such as ``Hf-Cr`` to the canonical ``Cr-Hf`` form."""
    canonical_name = canonicalize_system(system_name)
    if len(canonical_name.split("-")) != 2:
        raise ValueError(
            f"Expected a binary system like Cr-Hf, got {system_name!r}"
        )
    return canonical_name


def get_database_summary(
    connection: DuckDBPyConnection,
) -> DatabaseSummary:
    """Count the main curated entities currently available."""
    row = connection.execute(
        """
        SELECT
            (SELECT count(*) FROM alloy.sources),
            (SELECT count(*) FROM alloy.elements),
            (SELECT count(*) FROM alloy.alloy_systems),
            (SELECT count(*) FROM alloy.compositions),
            (SELECT count(*) FROM alloy.pairwise_interactions),
            (SELECT count(*) FROM alloy.calculation_runs),
            (SELECT count(*) FROM alloy.miscibility_predictions),
            (SELECT count(*) FROM alloy.pmr_predictions),
            (SELECT count(*) FROM alloy.predicted_phase_fractions),
            (SELECT count(*) FROM alloy.experimental_samples),
            (SELECT count(*) FROM alloy.thermodynamic_databases),
            (SELECT count(*) FROM alloy.documents),
            (SELECT count(*) FROM alloy.document_chunks),
            (SELECT count(*) FROM alloy.chunk_entities)
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("Database summary query returned no result")
    return DatabaseSummary(*map(int, row))


def list_documents(
    connection: DuckDBPyConnection,
) -> list[DocumentSummary]:
    """List ingested PDFs with evidence class and chunk counts."""
    rows = connection.execute(
        """
        SELECT
            d.title,
            d.authors,
            d.publication_year,
            src.source_class,
            src.authority_status,
            src.confidentiality,
            d.page_count,
            count(dc.chunk_id),
            src.source_id
        FROM alloy.documents AS d
        JOIN alloy.sources AS src USING (source_id)
        LEFT JOIN alloy.document_chunks AS dc USING (document_id)
        GROUP BY
            d.document_id,
            d.title,
            d.authors,
            d.publication_year,
            src.source_class,
            src.authority_status,
            src.confidentiality,
            d.page_count,
            src.source_id
        ORDER BY src.source_class, d.title
        """
    ).fetchall()
    return [
        DocumentSummary(
            title=str(row[0]),
            authors=None if row[1] is None else str(row[1]),
            publication_year=None if row[2] is None else int(row[2]),
            source_class=str(row[3]),
            authority_status=str(row[4]),
            confidentiality=str(row[5]),
            page_count=int(row[6]),
            chunk_count=int(row[7]),
            source_id=str(row[8]),
        )
        for row in rows
    ]


def search_document_chunks(
    connection: DuckDBPyConnection,
    query: str,
    *,
    limit: int = 5,
    source_class: str | None = None,
) -> list[DocumentChunkMatch]:
    """Run transparent keyword retrieval before embeddings are introduced."""
    terms = list(
        dict.fromkeys(
            term.lower()
            for term in re.findall(r"[A-Za-z0-9_-]+", query)
            if len(term) >= 2 and term.lower() not in _LEXICAL_STOPWORDS
        )
    )
    if not terms:
        raise ValueError("query must contain at least one searchable term")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    score_sql = " + ".join(
        "CASE WHEN lower(dc.chunk_text) LIKE ? THEN 1 ELSE 0 END"
        for _ in terms
    )
    match_sql = " OR ".join(
        "lower(dc.chunk_text) LIKE ?" for _ in terms
    )
    class_sql = "AND src.source_class = ?" if source_class else ""
    patterns = [f"%{term}%" for term in terms]
    parameters: list[object] = [
        *patterns,
        *patterns,
    ]
    if source_class:
        parameters.append(source_class)
    parameters.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            d.title,
            dc.page_start,
            dc.page_end,
            dc.section_title,
            dc.chunk_text,
            {score_sql} AS lexical_score,
            src.source_class,
            src.authority_status,
            src.source_id,
            dc.chunk_id
        FROM alloy.document_chunks AS dc
        JOIN alloy.documents AS d USING (document_id)
        JOIN alloy.sources AS src USING (source_id)
        WHERE ({match_sql})
        {class_sql}
        ORDER BY
            lexical_score DESC,
            CASE src.authority_status
                WHEN 'authoritative' THEN 0
                WHEN 'authoritative_curated' THEN 1
                WHEN 'supporting' THEN 2
                ELSE 3
            END,
            d.title,
            dc.chunk_index
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [
        DocumentChunkMatch(
            title=str(row[0]),
            page_start=int(row[1]),
            page_end=int(row[2]),
            section_title=None if row[3] is None else str(row[3]),
            chunk_text=str(row[4]),
            lexical_score=int(row[5]),
            source_class=str(row[6]),
            authority_status=str(row[7]),
            source_id=str(row[8]),
            chunk_id=str(row[9]),
        )
        for row in rows
    ]


def search_document_chunks_semantic(
    connection: DuckDBPyConnection,
    query_embedding: list[float],
    *,
    model_name: str,
    model_revision: str,
    limit: int = 5,
    source_class: str | None = None,
) -> list[SemanticChunkMatch]:
    """Retrieve chunks by cosine similarity to a precomputed query vector."""
    if len(query_embedding) != 384:
        raise ValueError("query_embedding must contain exactly 384 values")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    embedding_table = connection.execute(
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = 'alloy'
          AND table_name = 'chunk_embeddings'
        """
    ).fetchone()[0]
    if not embedding_table:
        raise RuntimeError("Embeddings have not been initialized")

    class_sql = "AND src.source_class = ?" if source_class else ""
    parameters: list[object] = [
        query_embedding,
        model_name,
        model_revision,
    ]
    if source_class:
        parameters.append(source_class)
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT
            d.title,
            dc.page_start,
            dc.page_end,
            dc.section_title,
            dc.chunk_text,
            array_cosine_similarity(
                ce.embedding,
                ?::FLOAT[384]
            ) AS cosine_similarity,
            src.source_class,
            src.authority_status,
            src.source_id,
            dc.chunk_id
        FROM alloy.chunk_embeddings AS ce
        JOIN alloy.document_chunks AS dc USING (chunk_id)
        JOIN alloy.documents AS d USING (document_id)
        JOIN alloy.sources AS src USING (source_id)
        WHERE ce.model_name = ?
          AND ce.model_revision = ?
        {class_sql}
        ORDER BY cosine_similarity DESC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [
        SemanticChunkMatch(
            title=str(row[0]),
            page_start=int(row[1]),
            page_end=int(row[2]),
            section_title=None if row[3] is None else str(row[3]),
            chunk_text=str(row[4]),
            cosine_similarity=float(row[5]),
            source_class=str(row[6]),
            authority_status=str(row[7]),
            source_id=str(row[8]),
            chunk_id=str(row[9]),
        )
        for row in rows
    ]


def get_system_overview(
    connection: DuckDBPyConnection,
    system_name: str,
) -> SystemOverview | None:
    """Summarize which structured evidence exists for one alloy system."""
    canonical_name = canonicalize_system(system_name)
    row = connection.execute(
        """
        SELECT
            s.canonical_name,
            s.n_components,
            (SELECT count(*)
             FROM alloy.compositions AS c
             WHERE c.system_id = s.system_id),
            (SELECT count(*)
             FROM alloy.miscibility_predictions AS mp
             JOIN alloy.compositions AS c USING (composition_id)
             WHERE c.system_id = s.system_id),
            (SELECT count(*)
             FROM alloy.pmr_predictions AS pp
             WHERE pp.system_id = s.system_id),
            (SELECT count(*)
             FROM alloy.predicted_phase_fractions AS ppf
             JOIN alloy.compositions AS c USING (composition_id)
             WHERE c.system_id = s.system_id),
            (SELECT count(*)
             FROM alloy.experimental_samples AS es
             JOIN alloy.compositions AS c USING (composition_id)
             WHERE c.system_id = s.system_id),
            EXISTS (
                SELECT 1
                FROM alloy.thermodynamic_databases AS tdb
                WHERE tdb.system_id = s.system_id
            )
        FROM alloy.alloy_systems AS s
        WHERE s.canonical_name = ?
        """,
        [canonical_name],
    ).fetchone()
    if row is None:
        return None
    return SystemOverview(
        canonical_name=str(row[0]),
        n_components=int(row[1]),
        composition_count=int(row[2]),
        miscibility_prediction_count=int(row[3]),
        pmr_prediction_count=int(row[4]),
        predicted_phase_fraction_count=int(row[5]),
        experimental_sample_count=int(row[6]),
        has_thermodynamic_database=bool(row[7]),
    )


_MISCIBILITY_RESULT_COLUMNS = """
    s.canonical_name,
    c.canonical_formula,
    c.original_formula,
    c.is_equimolar,
    mp.reported_miscibility_temperature_K,
    mp.miscibility_temperature_K,
    coalesce(
        metrics.melting_temperature_K,
        mp.legacy_melting_temperature_K
    ) AS melting_temperature_K,
    mp.miscibility_temperature_K / nullif(
        coalesce(
            metrics.melting_temperature_K,
            mp.legacy_melting_temperature_K
        ),
        0
    ) AS miscibility_ratio,
    mp.normalization_rule,
    mp.quality_flag,
    m.model_name,
    m.model_version,
    cr.result_source_id,
    mp.source_row_number
"""

_MISCIBILITY_RESULT_JOINS = """
    FROM alloy.miscibility_predictions AS mp
    JOIN alloy.miscibility_prediction_metrics AS metrics
      ON metrics.prediction_id = mp.prediction_id
    JOIN alloy.compositions AS c
      ON c.composition_id = mp.composition_id
    JOIN alloy.alloy_systems AS s USING (system_id)
    JOIN alloy.calculation_runs AS cr
      ON cr.run_id = mp.run_id
    JOIN alloy.models AS m USING (model_id)
"""


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _rows_to_miscibility_predictions(
    rows: list[tuple[object, ...]],
) -> list[MiscibilityPrediction]:
    return [
        MiscibilityPrediction(
            canonical_name=str(row[0]),
            canonical_formula=str(row[1]),
            original_formula=None if row[2] is None else str(row[2]),
            is_equimolar=bool(row[3]),
            reported_miscibility_temperature_K=float(row[4]),
            miscibility_temperature_K=float(row[5]),
            melting_temperature_K=_optional_float(row[6]),
            miscibility_ratio=_optional_float(row[7]),
            normalization_rule=str(row[8]),
            quality_flag=str(row[9]),
            model_name=str(row[10]),
            model_version=str(row[11]),
            source_id=str(row[12]),
            source_row_number=int(row[13]),
        )
        for row in rows
    ]


def get_miscibility_predictions_for_system(
    connection: DuckDBPyConnection,
    system_name: str,
    *,
    equimolar_only: bool = False,
) -> list[MiscibilityPrediction]:
    """Return every T_misc result for compositions in one alloy system."""
    canonical_name = canonicalize_system(system_name)
    equimolar_clause = "AND c.is_equimolar" if equimolar_only else ""
    rows = connection.execute(
        f"""
        SELECT {_MISCIBILITY_RESULT_COLUMNS}
        {_MISCIBILITY_RESULT_JOINS}
        WHERE s.canonical_name = ?
        {equimolar_clause}
        ORDER BY
            c.canonical_formula,
            mp.miscibility_temperature_K,
            m.model_name,
            mp.source_row_number
        """,
        [canonical_name],
    ).fetchall()
    return _rows_to_miscibility_predictions(rows)


def rank_equimolar_miscibility_predictions(
    connection: DuckDBPyConnection,
    *,
    limit: int = 10,
    descending: bool = True,
    n_components: int | None = None,
) -> list[MiscibilityPrediction]:
    """Rank curated equimolar compositions by normalized T_misc."""
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if n_components is not None and not 2 <= n_components <= 9:
        raise ValueError("n_components must be between 2 and 9")

    direction = "DESC" if descending else "ASC"
    component_clause = (
        "AND s.n_components = ?" if n_components is not None else ""
    )
    parameters: list[object] = []
    if n_components is not None:
        parameters.append(n_components)
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT {_MISCIBILITY_RESULT_COLUMNS}
        {_MISCIBILITY_RESULT_JOINS}
        WHERE c.is_equimolar
          AND mp.quality_flag = 'validated'
        {component_clause}
        ORDER BY
            mp.miscibility_temperature_K {direction},
            s.canonical_name
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return _rows_to_miscibility_predictions(rows)


def get_pmr_for_system(
    connection: DuckDBPyConnection,
    system_name: str,
    *,
    temperature_K: float | None = None,
) -> list[PmrPrediction]:
    """Return PMR values for a system, optionally at one exact temperature."""
    canonical_name = canonicalize_system(system_name)
    if temperature_K is not None and temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    temperature_clause = (
        "AND pp.temperature_K = ?" if temperature_K is not None else ""
    )
    parameters: list[object] = [canonical_name]
    if temperature_K is not None:
        parameters.append(temperature_K)
    rows = connection.execute(
        f"""
        SELECT
            s.canonical_name,
            pp.temperature_K,
            pp.pmr_percent,
            pp.grid_spacing_atomic_fraction,
            pp.quality_flag,
            m.model_name,
            m.model_version,
            cr.result_source_id,
            pp.source_row_number
        FROM alloy.pmr_predictions AS pp
        JOIN alloy.alloy_systems AS s USING (system_id)
        JOIN alloy.calculation_runs AS cr USING (run_id)
        JOIN alloy.models AS m USING (model_id)
        WHERE s.canonical_name = ?
        {temperature_clause}
        ORDER BY pp.temperature_K
        """,
        parameters,
    ).fetchall()
    return [
        PmrPrediction(
            canonical_name=str(row[0]),
            temperature_K=float(row[1]),
            pmr_percent=float(row[2]),
            grid_spacing_atomic_fraction=float(row[3]),
            quality_flag=str(row[4]),
            model_name=str(row[5]),
            model_version=str(row[6]),
            source_id=str(row[7]),
            source_row_number=int(row[8]),
        )
        for row in rows
    ]


def find_pmr_candidates(
    connection: DuckDBPyConnection,
    *,
    n_components: int | None = None,
    target_pmr_percent: float = 50.0,
    tolerance_percent: float = 25.0,
    temperature_K: float | None = None,
    limit: int = 10,
) -> list[PmrCandidate]:
    """Find distinct systems with PMR near a target value."""
    if n_components is not None and not 2 <= n_components <= 9:
        raise ValueError("n_components must be between 2 and 9")
    if not 0 <= target_pmr_percent <= 100:
        raise ValueError("target_pmr_percent must be between 0 and 100")
    if not 0 <= tolerance_percent <= 100:
        raise ValueError("tolerance_percent must be between 0 and 100")
    if temperature_K is not None and temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    component_clause = (
        "AND s.n_components = ?" if n_components is not None else ""
    )
    temperature_clause = (
        "AND pp.temperature_K = ?" if temperature_K is not None else ""
    )
    parameters: list[object] = [
        target_pmr_percent,
        target_pmr_percent,
        target_pmr_percent,
        tolerance_percent,
    ]
    if n_components is not None:
        parameters.append(n_components)
    if temperature_K is not None:
        parameters.append(temperature_K)
    parameters.extend([target_pmr_percent, target_pmr_percent, limit])
    rows = connection.execute(
        f"""
        SELECT
            s.canonical_name,
            s.n_components,
            pp.temperature_K,
            pp.pmr_percent,
            ? AS target_pmr_percent,
            abs(pp.pmr_percent - ?) AS distance_from_target_percent,
            pp.grid_spacing_atomic_fraction,
            pp.quality_flag,
            m.model_name,
            m.model_version,
            cr.result_source_id,
            pp.source_row_number
        FROM alloy.pmr_predictions AS pp
        JOIN alloy.alloy_systems AS s USING (system_id)
        JOIN alloy.calculation_runs AS cr USING (run_id)
        JOIN alloy.models AS m USING (model_id)
        WHERE abs(pp.pmr_percent - ?) <= ?
        {component_clause}
        {temperature_clause}
        QUALIFY row_number() OVER (
            PARTITION BY s.system_id
            ORDER BY
                abs(pp.pmr_percent - ?),
                pp.temperature_K,
                pp.source_row_number
        ) = 1
        ORDER BY
            abs(pp.pmr_percent - ?),
            s.canonical_name
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [
        PmrCandidate(
            canonical_name=str(row[0]),
            n_components=int(row[1]),
            temperature_K=float(row[2]),
            pmr_percent=float(row[3]),
            target_pmr_percent=float(row[4]),
            distance_from_target_percent=float(row[5]),
            grid_spacing_atomic_fraction=float(row[6]),
            quality_flag=str(row[7]),
            model_name=str(row[8]),
            model_version=str(row[9]),
            source_id=str(row[10]),
            source_row_number=int(row[11]),
        )
        for row in rows
    ]


def get_predicted_phases_for_system(
    connection: DuckDBPyConnection,
    system_name: str,
    *,
    temperature_K: float | None = None,
) -> list[PredictedPhaseFraction]:
    """Return recorded predicted phase fractions for one alloy system."""
    canonical_name = canonicalize_system(system_name)
    if temperature_K is not None and temperature_K <= 0:
        raise ValueError("temperature_K must be positive")
    temperature_clause = (
        "AND ppf.temperature_K = ?" if temperature_K is not None else ""
    )
    parameters: list[object] = [canonical_name]
    if temperature_K is not None:
        parameters.append(temperature_K)
    rows = connection.execute(
        f"""
        SELECT
            s.canonical_name,
            c.canonical_formula,
            ppf.temperature_K,
            ppf.raw_phase_label,
            p.phase_family,
            ppf.phase_fraction,
            m.model_name,
            cr.result_source_id,
            ppf.source_locator
        FROM alloy.predicted_phase_fractions AS ppf
        JOIN alloy.compositions AS c USING (composition_id)
        JOIN alloy.alloy_systems AS s USING (system_id)
        JOIN alloy.calculation_runs AS cr USING (run_id)
        JOIN alloy.models AS m USING (model_id)
        LEFT JOIN alloy.phases AS p USING (phase_id)
        WHERE s.canonical_name = ?
        {temperature_clause}
        ORDER BY
            c.canonical_formula,
            ppf.temperature_K,
            ppf.phase_fraction DESC,
            ppf.raw_phase_label
        """,
        parameters,
    ).fetchall()
    return [
        PredictedPhaseFraction(
            canonical_name=str(row[0]),
            canonical_formula=str(row[1]),
            temperature_K=float(row[2]),
            phase_name=str(row[3]),
            phase_family=None if row[4] is None else str(row[4]),
            phase_fraction=_optional_float(row[5]),
            model_name=str(row[6]),
            source_id=str(row[7]),
            source_locator=None if row[8] is None else str(row[8]),
        )
        for row in rows
    ]


def get_experimental_observations_for_system(
    connection: DuckDBPyConnection,
    system_name: str,
) -> list[ExperimentalObservation]:
    """Return source-preserving experimental reports without phase remapping."""
    canonical_name = canonicalize_system(system_name)
    rows = connection.execute(
        """
        SELECT
            s.canonical_name,
            c.canonical_formula,
            c.original_formula,
            es.sample_label,
            pe.route,
            pe.temperature_K,
            epo.raw_phase_label,
            es.provenance_status,
            es.source_id,
            epo.source_locator
        FROM alloy.experimental_samples AS es
        JOIN alloy.compositions AS c USING (composition_id)
        JOIN alloy.alloy_systems AS s USING (system_id)
        JOIN alloy.experimental_phase_observations AS epo USING (sample_id)
        LEFT JOIN alloy.processing_events AS pe
          ON pe.sample_id = es.sample_id
        WHERE s.canonical_name = ?
        ORDER BY
            c.canonical_formula,
            es.source_locator,
            pe.sequence_number
        """,
        [canonical_name],
    ).fetchall()
    return [
        ExperimentalObservation(
            canonical_name=str(row[0]),
            canonical_formula=str(row[1]),
            original_formula=None if row[2] is None else str(row[2]),
            sample_label=None if row[3] is None else str(row[3]),
            processing_route=None if row[4] is None else str(row[4]),
            processing_temperature_K=_optional_float(row[5]),
            raw_phase_label=str(row[6]),
            provenance_status=str(row[7]),
            source_id=str(row[8]),
            source_locator=None if row[9] is None else str(row[9]),
        )
        for row in rows
    ]


def get_tdb_coverage(
    connection: DuckDBPyConnection,
    system_name: str,
) -> ThermodynamicDatabaseCoverage | None:
    """Return TDB metadata, or an explicit no-database result for a system."""
    canonical_name = canonicalize_system(system_name)
    row = connection.execute(
        """
        SELECT
            s.canonical_name,
            tdb.source_id,
            src.original_path,
            tdb.phase_count,
            tdb.parameter_count,
            tdb.software_compatibility
        FROM alloy.alloy_systems AS s
        LEFT JOIN alloy.thermodynamic_databases AS tdb USING (system_id)
        LEFT JOIN alloy.sources AS src ON src.source_id = tdb.source_id
        WHERE s.canonical_name = ?
        """,
        [canonical_name],
    ).fetchone()
    if row is None:
        return None
    return ThermodynamicDatabaseCoverage(
        canonical_name=str(row[0]),
        has_database=row[1] is not None,
        source_id=None if row[1] is None else str(row[1]),
        original_path=None if row[2] is None else str(row[2]),
        phase_count=None if row[3] is None else int(row[3]),
        parameter_count=None if row[4] is None else int(row[4]),
        software_compatibility=None if row[5] is None else str(row[5]),
    )


_BINARY_RESULT_COLUMNS = """
    s.canonical_name,
    c.canonical_formula,
    pi.value_eV_atom,
    mp.reported_miscibility_temperature_K,
    mp.miscibility_temperature_K,
    mp.legacy_melting_temperature_K,
    mp.miscibility_temperature_K
        / mp.legacy_melting_temperature_K AS miscibility_ratio,
    mp.normalization_rule,
    mp.quality_flag,
    m.model_name,
    m.model_version,
    cr.result_source_id
"""

_BINARY_RESULT_JOINS = """
    FROM alloy.alloy_systems AS s
    JOIN alloy.compositions AS c
      ON c.system_id = s.system_id
     AND c.is_equimolar
    JOIN alloy.miscibility_predictions AS mp
      ON mp.composition_id = c.composition_id
    JOIN alloy.calculation_runs AS cr
      ON cr.run_id = mp.run_id
    JOIN alloy.models AS m
      ON m.model_id = cr.model_id
    JOIN alloy.pairwise_interactions AS pi
      ON pi.model_id = m.model_id
     AND pi.element_a || '-' || pi.element_b = s.canonical_name
     AND pi.source_id = cr.result_source_id
    WHERE s.n_components = 2
"""


def _rows_to_binary_summaries(
    rows: list[tuple[object, ...]],
) -> list[BinarySystemSummary]:
    return [
        BinarySystemSummary(
            canonical_name=str(row[0]),
            canonical_formula=str(row[1]),
            hmix_eV_atom=float(row[2]),
            reported_miscibility_temperature_K=float(row[3]),
            miscibility_temperature_K=float(row[4]),
            melting_temperature_K=float(row[5]),
            miscibility_ratio=float(row[6]),
            normalization_rule=str(row[7]),
            quality_flag=str(row[8]),
            model_name=str(row[9]),
            model_version=str(row[10]),
            source_id=str(row[11]),
        )
        for row in rows
    ]


def get_binary_system_summary(
    connection: DuckDBPyConnection,
    system_name: str,
) -> BinarySystemSummary | None:
    """Return the curated equimolar result for one binary system."""
    canonical_name = canonicalize_binary_system(system_name)
    rows = connection.execute(
        f"""
        SELECT {_BINARY_RESULT_COLUMNS}
        {_BINARY_RESULT_JOINS}
          AND s.canonical_name = ?
        ORDER BY cr.run_id
        """,
        [canonical_name],
    ).fetchall()
    summaries = _rows_to_binary_summaries(rows)

    if not summaries:
        return None
    if len(summaries) > 1:
        raise RuntimeError(
            f"Expected one result for {canonical_name}, found {len(summaries)}"
        )
    return summaries[0]


def get_pairwise_interactions_for_system(
    connection: DuckDBPyConnection,
    system_name: str,
) -> list[PairwiseInteraction]:
    """Return every stored binary interaction among a system's elements."""
    canonical_name = canonicalize_system(system_name)
    elements = canonical_name.split("-")
    placeholders = ", ".join("?" for _ in elements)
    rows = connection.execute(
        f"""
        SELECT
            pi.element_a,
            pi.element_b,
            pi.interaction_type,
            pi.value_eV_atom,
            m.model_name,
            m.model_version,
            pi.source_id
        FROM alloy.pairwise_interactions AS pi
        JOIN alloy.models AS m USING (model_id)
        WHERE pi.element_a IN ({placeholders})
          AND pi.element_b IN ({placeholders})
        ORDER BY pi.element_a, pi.element_b, m.model_name, pi.source_id
        """,
        [*elements, *elements],
    ).fetchall()
    return [
        PairwiseInteraction(
            requested_system=canonical_name,
            canonical_pair=f"{row[0]}-{row[1]}",
            element_a=str(row[0]),
            element_b=str(row[1]),
            interaction_type=str(row[2]),
            hmix_eV_atom=float(row[3]),
            model_name=str(row[4]),
            model_version=str(row[5]),
            source_id=str(row[6]),
        )
        for row in rows
    ]


def rank_binary_pairs_by_hmix(
    connection: DuckDBPyConnection,
    *,
    limit: int = 10,
    descending: bool = True,
) -> list[BinarySystemSummary]:
    """Rank binary systems by DFT pair mixing enthalpy in eV/atom."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    # SQL identifiers and keywords cannot be passed as query parameters.
    # The direction is safe because it is selected from two fixed literals.
    direction = "DESC" if descending else "ASC"
    rows = connection.execute(
        f"""
        SELECT {_BINARY_RESULT_COLUMNS}
        {_BINARY_RESULT_JOINS}
        ORDER BY pi.value_eV_atom {direction}, s.canonical_name
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return _rows_to_binary_summaries(rows)


def find_room_temperature_stable_binaries(
    connection: DuckDBPyConnection,
    *,
    room_temperature_K: float = 300.0,
) -> list[BinarySystemSummary]:
    """Find binaries whose predicted miscibility temperature is at or below RT."""
    if room_temperature_K <= 0:
        raise ValueError("room_temperature_K must be positive")

    rows = connection.execute(
        f"""
        SELECT {_BINARY_RESULT_COLUMNS}
        {_BINARY_RESULT_JOINS}
          AND mp.miscibility_temperature_K <= ?
        ORDER BY
            mp.miscibility_temperature_K,
            s.canonical_name
        """,
        [room_temperature_K],
    ).fetchall()
    return _rows_to_binary_summaries(rows)


def find_binaries_above_miscibility_temperature(
    connection: DuckDBPyConnection,
    minimum_temperature_K: float,
) -> list[BinarySystemSummary]:
    """Find binaries with normalized T_misc at or above a threshold."""
    if minimum_temperature_K <= 0:
        raise ValueError("minimum_temperature_K must be positive")

    rows = connection.execute(
        f"""
        SELECT {_BINARY_RESULT_COLUMNS}
        {_BINARY_RESULT_JOINS}
          AND mp.miscibility_temperature_K >= ?
        ORDER BY
            mp.miscibility_temperature_K DESC,
            s.canonical_name
        """,
        [minimum_temperature_K],
    ).fetchall()
    return _rows_to_binary_summaries(rows)
