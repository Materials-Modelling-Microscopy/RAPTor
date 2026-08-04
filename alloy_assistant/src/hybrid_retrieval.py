"""Hybrid lexical and semantic retrieval with transparent rank fusion."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from duckdb import DuckDBPyConnection

from .database import DEFAULT_DATABASE_PATH, connect
from .embeddings import (
    MODEL_NAME,
    MODEL_REVISION,
    encode_query,
)
from .queries import (
    DocumentChunkMatch,
    SemanticChunkMatch,
    search_document_chunks,
    search_document_chunks_semantic,
)


DEFAULT_RRF_K = 60
_AUTHORITY_WEIGHTS = {
    "authoritative": 1.05,
    "authoritative_curated": 1.04,
    "supporting": 1.0,
    "provisional": 0.95,
}
_SYSTEM_ENTITY_WEIGHT = 1.20
_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class HybridChunkMatch:
    """One citation-ready result with explainable fusion signals."""

    rank: int
    title: str
    citation: str
    page_start: int
    page_end: int
    section_title: str | None
    chunk_text: str
    hybrid_score: float
    retrieval_channels: str
    lexical_rank: int | None
    lexical_score: int | None
    semantic_rank: int | None
    cosine_similarity: float | None
    authority_status: str
    authority_weight: float
    requested_system: str | None
    system_entity_match: bool
    system_entity_weight: float
    source_class: str
    source_id: str
    chunk_id: str


def _citation(title: str, page_start: int, page_end: int) -> str:
    pages = (
        f"p. {page_start}"
        if page_start == page_end
        else f"pp. {page_start}-{page_end}"
    )
    return f"{title}, {pages}"


def _is_reference_chunk(
    text: str,
    section_title: str | None,
) -> bool:
    if section_title and section_title.strip().lower().startswith("reference"):
        return True
    return bool(
        re.match(
            r"^\s*(?:\d+\.\s*)?references?\s+(?:\[\s*1\s*\]|1\.)",
            text,
            re.I,
        )
    )


def _token_set(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN.findall(text)
        if len(token) > 2
    }


def _near_duplicate(
    candidate: dict[str, object],
    selected: list[dict[str, object]],
) -> bool:
    candidate_tokens = _token_set(str(candidate["chunk_text"]))
    if not candidate_tokens:
        return False
    for existing in selected:
        if candidate["source_id"] != existing["source_id"]:
            continue
        if candidate["page_start"] != existing["page_start"]:
            continue
        existing_tokens = _token_set(str(existing["chunk_text"]))
        union = candidate_tokens | existing_tokens
        if union and len(candidate_tokens & existing_tokens) / len(union) >= 0.65:
            return True
    return False


def _candidate_from_result(
    result: DocumentChunkMatch | SemanticChunkMatch,
) -> dict[str, object]:
    return {
        "title": result.title,
        "page_start": result.page_start,
        "page_end": result.page_end,
        "section_title": result.section_title,
        "chunk_text": result.chunk_text,
        "source_class": result.source_class,
        "authority_status": result.authority_status,
        "source_id": result.source_id,
        "chunk_id": result.chunk_id,
        "lexical_rank": None,
        "lexical_score": None,
        "semantic_rank": None,
        "cosine_similarity": None,
        "rrf_score": 0.0,
    }


def hybrid_search(
    connection: DuckDBPyConnection,
    query: str,
    *,
    query_embedding: list[float] | None = None,
    limit: int = 6,
    candidate_pool: int = 30,
    source_class: str | None = None,
    system_name: str | None = None,
    max_per_document: int = 3,
    max_total_words: int = 1800,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[HybridChunkMatch]:
    """Fuse lexical and semantic ranks into a compact evidence packet."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")
    if candidate_pool < limit or candidate_pool > 100:
        raise ValueError("candidate_pool must be between limit and 100")
    if max_per_document < 1:
        raise ValueError("max_per_document must be positive")
    if max_total_words < 100:
        raise ValueError("max_total_words must be at least 100")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    lexical = search_document_chunks(
        connection,
        query,
        limit=candidate_pool,
        source_class=source_class,
    )
    vector = query_embedding if query_embedding is not None else encode_query(query)
    semantic = search_document_chunks_semantic(
        connection,
        vector,
        model_name=MODEL_NAME,
        model_revision=MODEL_REVISION,
        limit=candidate_pool,
        source_class=source_class,
    )

    candidates: dict[str, dict[str, object]] = {}
    for rank, result in enumerate(lexical, start=1):
        item = candidates.setdefault(
            result.chunk_id,
            _candidate_from_result(result),
        )
        item["lexical_rank"] = rank
        item["lexical_score"] = result.lexical_score
        item["rrf_score"] = float(item["rrf_score"]) + 1.0 / (
            rrf_k + rank
        )
    for rank, result in enumerate(semantic, start=1):
        item = candidates.setdefault(
            result.chunk_id,
            _candidate_from_result(result),
        )
        item["semantic_rank"] = rank
        item["cosine_similarity"] = result.cosine_similarity
        item["rrf_score"] = float(item["rrf_score"]) + 1.0 / (
            rrf_k + rank
        )

    system_matches: set[str] = set()
    if system_name and candidates:
        placeholders = ", ".join("?" for _ in candidates)
        rows = connection.execute(
            f"""
            SELECT DISTINCT chunk_id
            FROM alloy.chunk_entities
            WHERE entity_type = 'alloy_system'
              AND entity_value = ?
              AND chunk_id IN ({placeholders})
            """,
            [system_name, *candidates],
        ).fetchall()
        system_matches = {str(row[0]) for row in rows}

    for item in candidates.values():
        authority = str(item["authority_status"])
        weight = _AUTHORITY_WEIGHTS.get(authority, 1.0)
        entity_match = str(item["chunk_id"]) in system_matches
        entity_weight = _SYSTEM_ENTITY_WEIGHT if entity_match else 1.0
        item["authority_weight"] = weight
        item["system_entity_match"] = entity_match
        item["system_entity_weight"] = entity_weight
        item["hybrid_score"] = (
            float(item["rrf_score"]) * weight * entity_weight
        )

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -float(item["hybrid_score"]),
            -float(item["cosine_similarity"] or -1),
            -int(item["lexical_score"] or -1),
            str(item["title"]),
            int(item["page_start"]),
        ),
    )

    selected: list[dict[str, object]] = []
    per_source: dict[str, int] = {}
    total_words = 0
    for item in ranked:
        if _is_reference_chunk(
            str(item["chunk_text"]),
            (
                None
                if item["section_title"] is None
                else str(item["section_title"])
            ),
        ):
            continue
        source_id = str(item["source_id"])
        if per_source.get(source_id, 0) >= max_per_document:
            continue
        if _near_duplicate(item, selected):
            continue
        word_count = len(str(item["chunk_text"]).split())
        if selected and total_words + word_count > max_total_words:
            continue
        selected.append(item)
        per_source[source_id] = per_source.get(source_id, 0) + 1
        total_words += word_count
        if len(selected) >= limit:
            break

    results: list[HybridChunkMatch] = []
    for rank, item in enumerate(selected, start=1):
        lexical_rank = item["lexical_rank"]
        semantic_rank = item["semantic_rank"]
        channels = (
            "lexical+semantic"
            if lexical_rank is not None and semantic_rank is not None
            else "lexical"
            if lexical_rank is not None
            else "semantic"
        )
        results.append(
            HybridChunkMatch(
                rank=rank,
                title=str(item["title"]),
                citation=_citation(
                    str(item["title"]),
                    int(item["page_start"]),
                    int(item["page_end"]),
                ),
                page_start=int(item["page_start"]),
                page_end=int(item["page_end"]),
                section_title=(
                    None
                    if item["section_title"] is None
                    else str(item["section_title"])
                ),
                chunk_text=str(item["chunk_text"]),
                hybrid_score=float(item["hybrid_score"]),
                retrieval_channels=channels,
                lexical_rank=(
                    None if lexical_rank is None else int(lexical_rank)
                ),
                lexical_score=(
                    None
                    if item["lexical_score"] is None
                    else int(item["lexical_score"])
                ),
                semantic_rank=(
                    None if semantic_rank is None else int(semantic_rank)
                ),
                cosine_similarity=(
                    None
                    if item["cosine_similarity"] is None
                    else float(item["cosine_similarity"])
                ),
                authority_status=str(item["authority_status"]),
                authority_weight=float(item["authority_weight"]),
                requested_system=system_name,
                system_entity_match=bool(item["system_entity_match"]),
                system_entity_weight=float(item["system_entity_weight"]),
                source_class=str(item["source_class"]),
                source_id=str(item["source_id"]),
                chunk_id=str(item["chunk_id"]),
            )
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve a fused, citation-ready evidence packet.",
    )
    parser.add_argument("query")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--candidate-pool", type=int, default=30)
    parser.add_argument("--source-class")
    parser.add_argument("--system-name")
    parser.add_argument("--max-per-document", type=int, default=3)
    parser.add_argument("--max-total-words", type=int, default=1800)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")
    with connect(database_path, read_only=True) as connection:
        results = hybrid_search(
            connection,
            args.query,
            limit=args.limit,
            candidate_pool=args.candidate_pool,
            source_class=args.source_class,
            system_name=args.system_name,
            max_per_document=args.max_per_document,
            max_total_words=args.max_total_words,
        )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        for result in results:
            print(
                f"[{result.rank}] {result.citation} "
                f"(hybrid={result.hybrid_score:.6f}, "
                f"channels={result.retrieval_channels})"
            )
            print(result.chunk_text)
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
