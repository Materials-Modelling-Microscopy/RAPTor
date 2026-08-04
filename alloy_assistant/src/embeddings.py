"""Local, versioned embeddings for Alloy Assistant document chunks."""

from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from duckdb import DuckDBPyConnection

from .database import ALLOY_ASSISTANT_ROOT, DEFAULT_DATABASE_PATH, connect
from .ingestion_common import transaction
from .normalization import stable_id
from .validate_schema import format_validation, inspect_schema


MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "baab320e3049c6c62dd63560765566dd9083985e"
EMBEDDING_DIMENSION = 384
QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)
MODEL_CACHE = ALLOY_ASSISTANT_ROOT / "data" / "generated" / "models"

_EMBEDDING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS alloy.chunk_embeddings (
    embedding_id VARCHAR PRIMARY KEY,
    chunk_id VARCHAR NOT NULL
        REFERENCES alloy.document_chunks(chunk_id),
    model_name VARCHAR NOT NULL,
    model_revision VARCHAR NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (
        embedding_dimension = 384
    ),
    text_sha256 VARCHAR NOT NULL,
    embedding FLOAT[384] NOT NULL,
    normalized BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (chunk_id, model_name, model_revision)
)
"""


@dataclass(frozen=True)
class EmbeddingReport:
    """Result of embedding the current document chunks."""

    model_name: str
    model_revision: str
    embedding_dimension: int
    chunks_discovered: int
    chunks_embedded: int
    chunks_skipped: int
    embeddings_stored: int


def ensure_embedding_schema(connection: DuckDBPyConnection) -> None:
    """Lazily migrate an existing database to support embeddings."""
    connection.execute(_EMBEDDING_TABLE_SQL)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def load_embedding_model():
    """Load the pinned local model once per Python process."""
    cache_root = MODEL_CACHE.resolve()
    os.environ["HF_HOME"] = str(cache_root / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(cache_root / "huggingface" / "hub")
    os.environ["HF_XET_CACHE"] = str(cache_root / "huggingface" / "xet")
    os.environ["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    from sentence_transformers import SentenceTransformer

    cache_root.mkdir(parents=True, exist_ok=True)
    model_kwargs = {
        "revision": MODEL_REVISION,
        "cache_folder": str(cache_root),
    }
    try:
        model = SentenceTransformer(
            MODEL_NAME,
            local_files_only=True,
            **model_kwargs,
        )
    except OSError:
        model = SentenceTransformer(
            MODEL_NAME,
            local_files_only=False,
            **model_kwargs,
        )
    if model.get_embedding_dimension() != EMBEDDING_DIMENSION:
        raise RuntimeError(
            "Unexpected embedding dimension: "
            f"{model.get_embedding_dimension()}"
        )
    return model


def _encode_documents(texts: list[str], *, batch_size: int) -> list[list[float]]:
    model = load_embedding_model()
    vectors = model.encode_document(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > batch_size,
    )
    return vectors.astype("float32").tolist()


def encode_query(query: str) -> list[float]:
    """Embed a short search query using the model's retrieval instruction."""
    text = query.strip()
    if not text:
        raise ValueError("query must not be empty")
    model = load_embedding_model()
    vector = model.encode_query(
        QUERY_INSTRUCTION + text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vector.astype("float32").tolist()


def embed_document_chunks(
    connection: DuckDBPyConnection,
    *,
    rebuild: bool = False,
    batch_size: int = 32,
    encoder: Callable[[list[str], int], list[list[float]]] | None = None,
) -> EmbeddingReport:
    """Embed new or changed chunks and persist their normalized vectors."""
    if batch_size < 1 or batch_size > 512:
        raise ValueError("batch_size must be between 1 and 512")
    ensure_embedding_schema(connection)

    if rebuild:
        with transaction(connection):
            connection.execute(
                """
                DELETE FROM alloy.chunk_embeddings
                WHERE model_name = ? AND model_revision = ?
                """,
                [MODEL_NAME, MODEL_REVISION],
            )

    rows = connection.execute(
        """
        SELECT
            dc.chunk_id,
            dc.chunk_text,
            ce.text_sha256
        FROM alloy.document_chunks AS dc
        LEFT JOIN alloy.chunk_embeddings AS ce
          ON ce.chunk_id = dc.chunk_id
         AND ce.model_name = ?
         AND ce.model_revision = ?
        ORDER BY dc.document_id, dc.chunk_index
        """,
        [MODEL_NAME, MODEL_REVISION],
    ).fetchall()
    pending = [
        (str(chunk_id), str(text), _text_sha256(str(text)))
        for chunk_id, text, stored_sha in rows
        if stored_sha is None or str(stored_sha) != _text_sha256(str(text))
    ]

    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        texts = [text for _, text, _ in batch]
        vectors = (
            encoder(texts, batch_size)
            if encoder is not None
            else _encode_documents(texts, batch_size=batch_size)
        )
        if any(len(vector) != EMBEDDING_DIMENSION for vector in vectors):
            raise ValueError("encoder returned an unexpected vector dimension")
        with transaction(connection):
            for (chunk_id, _, text_sha), vector in zip(batch, vectors):
                connection.execute(
                    """
                    INSERT INTO alloy.chunk_embeddings (
                        embedding_id,
                        chunk_id,
                        model_name,
                        model_revision,
                        embedding_dimension,
                        text_sha256,
                        embedding,
                        normalized
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?::FLOAT[384], TRUE)
                    ON CONFLICT (
                        chunk_id,
                        model_name,
                        model_revision
                    )
                    DO UPDATE SET
                        embedding_dimension = excluded.embedding_dimension,
                        text_sha256 = excluded.text_sha256,
                        embedding = excluded.embedding,
                        normalized = excluded.normalized,
                        created_at = now()
                    """,
                    [
                        stable_id(
                            "embedding",
                            chunk_id,
                            MODEL_NAME,
                            MODEL_REVISION,
                        ),
                        chunk_id,
                        MODEL_NAME,
                        MODEL_REVISION,
                        EMBEDDING_DIMENSION,
                        text_sha,
                        vector,
                    ],
                )

    stored = int(
        connection.execute(
            """
            SELECT count(*)
            FROM alloy.chunk_embeddings
            WHERE model_name = ? AND model_revision = ?
            """,
            [MODEL_NAME, MODEL_REVISION],
        ).fetchone()[0]
    )
    return EmbeddingReport(
        model_name=MODEL_NAME,
        model_revision=MODEL_REVISION,
        embedding_dimension=EMBEDDING_DIMENSION,
        chunks_discovered=len(rows),
        chunks_embedded=len(pending),
        chunks_skipped=len(rows) - len(pending),
        embeddings_stored=stored,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create local vector embeddings for document chunks.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate every vector for the pinned model.",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")
    with connect(database_path) as connection:
        ensure_embedding_schema(connection)
        validation = inspect_schema(connection)
        if not validation.is_valid:
            raise RuntimeError(format_validation(validation))
        report = embed_document_chunks(
            connection,
            rebuild=args.rebuild,
            batch_size=args.batch_size,
        )
    for field, value in report.__dict__.items():
        print(f"{field}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
