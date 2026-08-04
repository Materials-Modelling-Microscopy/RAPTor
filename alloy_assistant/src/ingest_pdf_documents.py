"""Ingest page-aware PDF chunks into the Alloy Assistant database."""

from __future__ import annotations

import argparse
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from duckdb import DuckDBPyConnection
from pypdf import PdfReader

from .database import ALLOY_ASSISTANT_ROOT, DEFAULT_DATABASE_PATH, connect
from .ingestion_common import (
    register_source,
    source_exists,
    source_identity,
    transaction,
)
from .normalization import (
    ELEMENTS,
    canonical_system_name,
    parse_composition_formula,
    stable_id,
)
from .validate_schema import format_validation, inspect_schema


logging.getLogger("pypdf").setLevel(logging.ERROR)

PDF_ROOT = ALLOY_ASSISTANT_ROOT / "data" / "inbox"
PARSER_VERSION = "pypdf-6.10.0-page-word-v1"
DEFAULT_MAX_WORDS = 350
DEFAULT_OVERLAP_WORDS = 40

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9([])")
_BARE_PAGE_NUMBER = re.compile(r"^(?:page\s+)?\d+(?:\s+of\s+\d+)?$", re.I)
_COMMENT_NOISE = re.compile(
    r"(?:Formatted:|Deleted:|Commented\s*\[|Comment\s*\[)",
    re.I,
)
_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(Abstract|Introduction|Background|Methods?|Methodology|"
    r"Results?(?:\s+and\s+Discussion)?|Discussion|Conclusions?|"
    r"Summary|References|Acknowledg(?:e)?ments?|Supplementary Information)"
    r"\s*$",
    re.I,
)
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
_YEAR_IN_NAME = re.compile(r"\b(19|20)\d{2}\b")

_ELEMENT_PATTERN = "|".join(
    sorted(ELEMENTS, key=len, reverse=True)
)
_HYPHEN_SYSTEM = re.compile(
    rf"(?<![A-Za-z])({_ELEMENT_PATTERN})"
    rf"(?:-({_ELEMENT_PATTERN}))+(?![A-Za-z])"
)
_COMPACT_COMPOSITION = re.compile(
    rf"(?<![A-Za-z])"
    rf"(?:(?:{_ELEMENT_PATTERN})(?:\d+(?:\.\d+)?)?){{2,}}"
    rf"(?![a-z])"
)
_PHASE_TERMS = {
    "BCC": re.compile(r"\bBCC(?:_A2)?\b", re.I),
    "B2": re.compile(r"\bB2\b"),
    "FCC": re.compile(r"\bFCC(?:_A1)?\b", re.I),
    "HCP": re.compile(r"\bHCP(?:_A3)?\b", re.I),
    "Laves": re.compile(r"\bLaves\b", re.I),
    "sigma": re.compile(r"\bsigma(?:\s+phase)?\b", re.I),
    "intermetallic": re.compile(r"\bintermetallics?\b", re.I),
}
_METHOD_TERMS = {
    "DFT": re.compile(r"\bDFT\b|\bdensity functional theory\b", re.I),
    "CALPHAD": re.compile(r"\bCALPHAD\b", re.I),
    "ab initio": re.compile(r"\bab initio\b", re.I),
    "regular solution": re.compile(r"\bregular solution\b", re.I),
    "XRD": re.compile(r"\bXRD\b|\bX-ray diffraction\b", re.I),
    "SEM": re.compile(r"\bSEM\b|\bscanning electron microscopy\b", re.I),
    "TEM": re.compile(r"\bTEM\b|\btransmission electron microscopy\b", re.I),
    "additive manufacturing": re.compile(
        r"\badditive manufacturing\b|\bdirected energy deposition\b",
        re.I,
    ),
}
_CONCEPT_TERMS = {
    "miscibility": re.compile(r"\bmiscib(?:ility|le)\b", re.I),
    "mixing enthalpy": re.compile(r"\bmixing enthalp(?:y|ies)\b", re.I),
    "spinodal decomposition": re.compile(
        r"\bspinodal decomposition\b",
        re.I,
    ),
    "phase stability": re.compile(r"\bphase stability\b", re.I),
    "solid solution": re.compile(r"\bsolid solutions?\b", re.I),
    "high-entropy alloy": re.compile(
        r"\bhigh[- ]entropy alloys?\b|\bHEAs?\b",
        re.I,
    ),
}


@dataclass(frozen=True)
class ExtractedChunk:
    """One page-local text chunk before database insertion."""

    page_number: int
    section_title: str | None
    text: str


@dataclass(frozen=True)
class PdfIngestionReport:
    """Counts produced by a PDF ingestion run."""

    files_discovered: int
    files_registered: int
    files_already_registered: int
    files_rebuilt: int
    documents: int
    pages: int
    chunks: int
    entity_annotations: int


def _normalized_margin_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def _repeated_margin_lines(page_texts: list[str]) -> set[str]:
    """Find lines repeatedly occurring near page tops or bottoms."""
    counts: Counter[str] = Counter()
    for text in page_texts:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        candidates = {
            _normalized_margin_line(line)
            for line in lines[:3] + lines[-3:]
            if len(line.strip()) >= 4
        }
        counts.update(candidates)
    threshold = max(3, math.ceil(len(page_texts) * 0.2))
    return {line for line, count in counts.items() if count >= threshold}


def _clean_page_text(text: str, repeated_margins: set[str]) -> str:
    """Remove common PDF noise and join visual lines into prose."""
    kept: list[str] = []
    for raw_line in text.replace("\u00ad", "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if _normalized_margin_line(line) in repeated_margins:
            continue
        if _BARE_PAGE_NUMBER.fullmatch(line):
            continue
        if _COMMENT_NOISE.search(line):
            continue
        if kept and kept[-1].endswith("-") and line[:1].islower():
            kept[-1] = kept[-1][:-1] + line
        else:
            kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _section_for_page(raw_text: str, previous: str | None) -> str | None:
    section = previous
    for line in raw_text.splitlines():
        candidate = re.sub(r"\s+", " ", line).strip()
        match = _HEADING.fullmatch(candidate)
        if match:
            section = match.group(1).title()
    return section


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    return [
        " ".join(words[index : index + max_words])
        for index in range(0, len(words), max_words)
    ]


def chunk_page_text(
    text: str,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    """Split cleaned page text into sentence-respecting word-limited chunks."""
    if max_words < 50:
        raise ValueError("max_words must be at least 50")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be >= 0 and less than max_words")
    if not text.strip():
        return []

    sentences: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(text.strip()):
        if len(sentence.split()) > max_words:
            sentences.extend(_split_long_sentence(sentence, max_words))
        elif sentence.strip():
            sentences.append(sentence.strip())

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and current_words + sentence_words > max_words:
            chunks.append(" ".join(current))
            overlap: list[str] = []
            overlap_count = 0
            for prior in reversed(current):
                prior_words = len(prior.split())
                if overlap_count + prior_words > overlap_words:
                    break
                overlap.insert(0, prior)
                overlap_count += prior_words
            current = overlap
            current_words = overlap_count
        current.append(sentence)
        current_words += sentence_words
    if current:
        final = " ".join(current)
        if not chunks or final != chunks[-1]:
            chunks.append(final)
    return chunks


def _extract_pdf(
    path: Path,
    *,
    max_words: int,
    overlap_words: int,
) -> tuple[PdfReader, list[str], list[ExtractedChunk]]:
    reader = PdfReader(path)
    page_texts = [page.extract_text() or "" for page in reader.pages]
    repeated_margins = _repeated_margin_lines(page_texts)
    chunks: list[ExtractedChunk] = []
    current_section: str | None = None
    for page_number, raw_text in enumerate(page_texts, start=1):
        current_section = _section_for_page(raw_text, current_section)
        cleaned = _clean_page_text(raw_text, repeated_margins)
        for text in chunk_page_text(
            cleaned,
            max_words=max_words,
            overlap_words=overlap_words,
        ):
            chunks.append(
                ExtractedChunk(
                    page_number=page_number,
                    section_title=current_section,
                    text=text,
                )
            )
    return reader, page_texts, chunks


def _metadata(
    path: Path,
    reader: PdfReader,
    page_texts: list[str],
) -> dict[str, object]:
    pdf_metadata = reader.metadata or {}
    embedded_title = str(pdf_metadata.get("/Title") or "").strip()
    embedded_author = str(pdf_metadata.get("/Author") or "").strip()
    stem = path.stem.replace("_", " ").strip()
    publication_match = re.match(
        r"(.+?)\s+-\s+((?:19|20)\d{2})\s+-\s+(.+)",
        stem,
    )
    if embedded_title:
        title = embedded_title
    elif publication_match:
        title = publication_match.group(3)
    else:
        title = stem

    authors = embedded_author or (
        publication_match.group(1) if publication_match else None
    )
    year_match = _YEAR_IN_NAME.search(stem)
    publication_year = int(year_match.group(0)) if year_match else None
    opening_text = " ".join(page_texts[:2])
    doi_match = _DOI.search(opening_text)

    category = path.relative_to(PDF_ROOT).parts[0]
    if category == "dissertation":
        source_class = "dissertation"
        confidentiality = "unpublished"
        authority = "authoritative"
    elif category == "manuscripts":
        source_class = "manuscript"
        confidentiality = "unpublished"
        authority = "authoritative"
    elif re.search(r"\bPravan\s+Omprakash\b", opening_text, re.I):
        source_class = "own_publication"
        confidentiality = "public"
        authority = "authoritative"
    else:
        source_class = "external_literature"
        confidentiality = "public"
        authority = "supporting"

    return {
        "title": title[:1000],
        "authors": authors,
        "publication_year": publication_year,
        "doi": doi_match.group(0).rstrip(".,;)") if doi_match else None,
        "source_class": source_class,
        "confidentiality": confidentiality,
        "authority": authority,
    }


def _entities(text: str) -> set[tuple[str, str]]:
    entities: set[tuple[str, str]] = set()
    for match in _HYPHEN_SYSTEM.finditer(text):
        raw = match.group(0)
        try:
            fractions = parse_composition_formula(raw.replace("-", ""))
        except ValueError:
            continue
        elements = tuple(sorted(fractions))
        entities.add(("alloy_system", canonical_system_name(elements)))
        entities.update(("element", element) for element in elements)
    for match in _COMPACT_COMPOSITION.finditer(text):
        raw = match.group(0)
        try:
            fractions = parse_composition_formula(raw)
        except ValueError:
            continue
        if len(fractions) < 2:
            continue
        elements = tuple(sorted(fractions))
        entities.add(("alloy_system", canonical_system_name(elements)))
        entities.update(("element", element) for element in elements)
    for name, pattern in _PHASE_TERMS.items():
        if pattern.search(text):
            entities.add(("phase", name))
    for name, pattern in _METHOD_TERMS.items():
        if pattern.search(text):
            entities.add(("method", name))
    for name, pattern in _CONCEPT_TERMS.items():
        if pattern.search(text):
            entities.add(("concept", name))
    return entities


def _existing_document_counts(
    connection: DuckDBPyConnection,
    source_id: str,
) -> tuple[str, int, int]:
    row = connection.execute(
        """
        SELECT
            d.document_id,
            count(DISTINCT dc.chunk_id),
            count(ce.entity_value)
        FROM alloy.documents AS d
        LEFT JOIN alloy.document_chunks AS dc USING (document_id)
        LEFT JOIN alloy.chunk_entities AS ce USING (chunk_id)
        WHERE d.source_id = ?
        GROUP BY d.document_id
        """,
        [source_id],
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Source has no document record: {source_id}")
    return str(row[0]), int(row[1]), int(row[2])


def _ingest_pdf(
    connection: DuckDBPyConnection,
    path: Path,
    *,
    rebuild: bool,
    max_words: int,
    overlap_words: int,
) -> tuple[str, int, int, int]:
    source_id, checksum = source_identity(path)
    existing_source = source_exists(connection, sha256=checksum)
    existing_document = None
    if existing_source is not None:
        existing_document = connection.execute(
            "SELECT document_id FROM alloy.documents WHERE source_id = ?",
            [existing_source],
        ).fetchone()
        if existing_document is not None and not rebuild:
            _, chunks, entities = _existing_document_counts(
                connection,
                existing_source,
            )
            page_count = int(
                connection.execute(
                    "SELECT page_count FROM alloy.documents WHERE source_id = ?",
                    [existing_source],
                ).fetchone()[0]
            )
            return "existing", page_count, chunks, entities

    reader, page_texts, chunks = _extract_pdf(
        path,
        max_words=max_words,
        overlap_words=overlap_words,
    )
    metadata = _metadata(path, reader, page_texts)
    document_id = stable_id("document", source_id)

    if existing_document is not None:
        # DuckDB cannot delete child and parent rows affected by the same
        # foreign key in one transaction. Commit annotation removal first;
        # the unchanged PDF remains the recoverable source of truth.
        with transaction(connection):
            embedding_table_exists = connection.execute(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'alloy'
                  AND table_name = 'chunk_embeddings'
                """
            ).fetchone()[0]
            if embedding_table_exists:
                connection.execute(
                    """
                    DELETE FROM alloy.chunk_embeddings
                    WHERE chunk_id IN (
                        SELECT chunk_id
                        FROM alloy.document_chunks
                        WHERE document_id = ?
                    )
                    """,
                    [document_id],
                )
            connection.execute(
                """
                DELETE FROM alloy.chunk_entities
                WHERE chunk_id IN (
                    SELECT chunk_id
                    FROM alloy.document_chunks
                    WHERE document_id = ?
                )
                """,
                [document_id],
            )

    with transaction(connection):
        if existing_source is None:
            register_source(
                connection,
                path=path,
                source_id=source_id,
                sha256=checksum,
                source_class=str(metadata["source_class"]),
                title=str(metadata["title"]),
                authority_status=str(metadata["authority"]),
                confidentiality=str(metadata["confidentiality"]),
                version_label=PARSER_VERSION,
                notes="Page-aware prototype PDF extraction.",
            )
        if existing_document is not None:
            connection.execute(
                "DELETE FROM alloy.document_chunks WHERE document_id = ?",
                [document_id],
            )
            connection.execute(
                """
                UPDATE alloy.documents
                SET
                    title = ?,
                    authors = ?,
                    publication_year = ?,
                    doi = ?,
                    page_count = ?,
                    parse_status = 'parsed'
                WHERE document_id = ?
                """,
                [
                    metadata["title"],
                    metadata["authors"],
                    metadata["publication_year"],
                    metadata["doi"],
                    len(reader.pages),
                    document_id,
                ],
            )
        else:
            connection.execute(
                """
                INSERT INTO alloy.documents (
                    document_id,
                    source_id,
                    title,
                    authors,
                    publication_year,
                    doi,
                    page_count,
                    parse_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'parsed')
                """,
                [
                    document_id,
                    source_id,
                    metadata["title"],
                    metadata["authors"],
                    metadata["publication_year"],
                    metadata["doi"],
                    len(reader.pages),
                ],
            )

        entity_count = 0
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = stable_id(
                "chunk",
                document_id,
                str(chunk_index),
                PARSER_VERSION,
                str(max_words),
                str(overlap_words),
            )
            connection.execute(
                """
                INSERT INTO alloy.document_chunks (
                    chunk_id,
                    document_id,
                    chunk_index,
                    section_title,
                    page_start,
                    page_end,
                    chunk_text,
                    parser_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    chunk_id,
                    document_id,
                    chunk_index,
                    chunk.section_title,
                    chunk.page_number,
                    chunk.page_number,
                    chunk.text,
                    PARSER_VERSION,
                ],
            )
            entities = sorted(_entities(chunk.text))
            if entities:
                connection.executemany(
                    """
                    INSERT INTO alloy.chunk_entities (
                        chunk_id,
                        entity_type,
                        entity_value
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        (chunk_id, entity_type, entity_value)
                        for entity_type, entity_value in entities
                    ],
                )
            entity_count += len(entities)

    status = "rebuilt" if existing_document is not None else "registered"
    return status, len(reader.pages), len(chunks), entity_count


def ingest_pdf_documents(
    connection: DuckDBPyConnection,
    *,
    rebuild: bool = False,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> PdfIngestionReport:
    """Ingest every PDF below the document inbox."""
    paths = sorted(PDF_ROOT.rglob("*.pdf"))
    if not paths:
        raise FileNotFoundError(f"No PDFs found below {PDF_ROOT}")

    registered = existing = rebuilt = pages = chunks = entities = 0
    for path in paths:
        status, page_count, chunk_count, entity_count = _ingest_pdf(
            connection,
            path,
            rebuild=rebuild,
            max_words=max_words,
            overlap_words=overlap_words,
        )
        registered += status == "registered"
        existing += status == "existing"
        rebuilt += status == "rebuilt"
        pages += page_count
        chunks += chunk_count
        entities += entity_count

    documents = int(
        connection.execute("SELECT count(*) FROM alloy.documents").fetchone()[0]
    )
    return PdfIngestionReport(
        files_discovered=len(paths),
        files_registered=registered,
        files_already_registered=existing,
        files_rebuilt=rebuilt,
        documents=documents,
        pages=pages,
        chunks=chunks,
        entity_annotations=entities,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and chunk all Alloy Assistant PDF documents.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Replace existing chunks for unchanged PDFs.",
    )
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument(
        "--overlap-words",
        type=int,
        default=DEFAULT_OVERLAP_WORDS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")
    with connect(database_path) as connection:
        validation = inspect_schema(connection)
        if not validation.is_valid:
            raise RuntimeError(format_validation(validation))
        report = ingest_pdf_documents(
            connection,
            rebuild=args.rebuild,
            max_words=args.max_words,
            overlap_words=args.overlap_words,
        )
    for field, value in report.__dict__.items():
        print(f"{field}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
