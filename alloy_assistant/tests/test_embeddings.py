"""Tests for versioned embedding storage and semantic retrieval."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.embeddings import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    MODEL_REVISION,
    embed_document_chunks,
)
from alloy_assistant.src.queries import search_document_chunks_semantic


class EmbeddingPipelineTest(unittest.TestCase):
    """Use a deterministic fake encoder; tests never download a model."""

    def setUp(self) -> None:
        self.manager = connect(":memory:")
        self.connection = self.manager.__enter__()
        initialize_schema(self.connection)
        self.connection.execute(
            """
            INSERT INTO alloy.sources (
                source_id,
                source_class,
                title,
                original_path,
                sha256,
                version_label,
                confidentiality,
                authority_status
            )
            VALUES (
                'source_test',
                'manuscript',
                'Test document',
                'test.pdf',
                repeat('a', 64),
                'test',
                'unpublished',
                'authoritative'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO alloy.documents
            VALUES (
                'document_test',
                'source_test',
                'Test document',
                'Test Author',
                NULL,
                NULL,
                1,
                'parsed'
            )
            """
        )
        self.connection.execute(
            """
            INSERT INTO alloy.document_chunks
            VALUES (
                'chunk_test',
                'document_test',
                0,
                'Results',
                1,
                1,
                'Spinodal decomposition is controlled by pair repulsion.',
                'test-parser'
            )
            """
        )

    def tearDown(self) -> None:
        self.manager.__exit__(None, None, None)

    @staticmethod
    def _fake_encoder(
        texts: list[str],
        batch_size: int,
    ) -> list[list[float]]:
        del batch_size
        return [
            [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
            for _ in texts
        ]

    def test_embedding_storage_is_idempotent_and_stale_aware(self) -> None:
        first = embed_document_chunks(
            self.connection,
            encoder=self._fake_encoder,
        )
        self.assertEqual(first.chunks_embedded, 1)
        self.assertEqual(first.embeddings_stored, 1)

        second = embed_document_chunks(
            self.connection,
            encoder=self._fake_encoder,
        )
        self.assertEqual(second.chunks_embedded, 0)
        self.assertEqual(second.chunks_skipped, 1)

        self.connection.execute(
            """
            UPDATE alloy.document_chunks
            SET chunk_text = chunk_text || ' Updated.'
            WHERE chunk_id = 'chunk_test'
            """
        )
        refreshed = embed_document_chunks(
            self.connection,
            encoder=self._fake_encoder,
        )
        self.assertEqual(refreshed.chunks_embedded, 1)
        self.assertEqual(refreshed.embeddings_stored, 1)

    def test_semantic_query_uses_duckdb_cosine_similarity(self) -> None:
        embed_document_chunks(
            self.connection,
            encoder=self._fake_encoder,
        )
        query = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
        results = search_document_chunks_semantic(
            self.connection,
            query,
            model_name=MODEL_NAME,
            model_revision=MODEL_REVISION,
        )
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0].cosine_similarity, 1.0)
        self.assertEqual(results[0].page_start, 1)
        self.assertEqual(results[0].source_class, "manuscript")


if __name__ == "__main__":
    unittest.main()
