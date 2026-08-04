"""Deterministic tests for hybrid reciprocal-rank fusion."""

from __future__ import annotations

import math
import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.embeddings import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    MODEL_REVISION,
)
from alloy_assistant.src.hybrid_retrieval import hybrid_search


class HybridRetrievalTest(unittest.TestCase):
    """Build a tiny corpus with lexical-only and semantic-only evidence."""

    def setUp(self) -> None:
        self.manager = connect(":memory:")
        self.connection = self.manager.__enter__()
        initialize_schema(self.connection)
        self._insert_source("source_a", "manuscript", "a" * 64)
        self._insert_source(
            "source_b",
            "external_literature",
            "b" * 64,
            authority="supporting",
        )
        self._insert_document("document_a", "source_a", "Primary study")
        self._insert_document("document_b", "source_b", "Supporting study")

        self._insert_chunk(
            "chunk_both",
            "document_a",
            0,
            4,
            "Results",
            "Spinodal decomposition is controlled by pair repulsion.",
            self._vector(1.0, 0.0),
        )
        self._insert_chunk(
            "chunk_lexical",
            "document_a",
            1,
            5,
            "Discussion",
            "A spinodal pair interaction appears in this passage.",
            self._vector(0.0, 1.0),
        )
        self._insert_chunk(
            "chunk_semantic",
            "document_b",
            0,
            8,
            "Results",
            "Chemical instability emerges from strongly unfavorable atomic interactions.",
            self._vector(0.9, math.sqrt(0.19)),
        )
        self.connection.execute(
            """
            INSERT INTO alloy.chunk_entities
            VALUES ('chunk_semantic', 'alloy_system', 'Mo-Nb-Ta-W')
            """
        )
        self._insert_chunk(
            "chunk_reference",
            "document_b",
            1,
            12,
            "References",
            "References [1] Spinodal decomposition pair repulsion.",
            self._vector(1.0, 0.0),
        )

    def tearDown(self) -> None:
        self.manager.__exit__(None, None, None)

    def _insert_source(
        self,
        source_id: str,
        source_class: str,
        sha256: str,
        *,
        authority: str = "authoritative",
    ) -> None:
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
            VALUES (?, ?, ?, ?, ?, 'test', 'internal', ?)
            """,
            [
                source_id,
                source_class,
                source_id,
                f"{source_id}.pdf",
                sha256,
                authority,
            ],
        )

    def _insert_document(
        self,
        document_id: str,
        source_id: str,
        title: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO alloy.documents
            VALUES (?, ?, ?, NULL, NULL, NULL, 20, 'parsed')
            """,
            [document_id, source_id, title],
        )

    @staticmethod
    def _vector(first: float, second: float) -> list[float]:
        return [first, second] + [0.0] * (EMBEDDING_DIMENSION - 2)

    def _insert_chunk(
        self,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        page: int,
        section: str,
        text: str,
        vector: list[float],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO alloy.document_chunks
            VALUES (?, ?, ?, ?, ?, ?, ?, 'test-parser')
            """,
            [
                chunk_id,
                document_id,
                chunk_index,
                section,
                page,
                page,
                text,
            ],
        )
        self.connection.execute(
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
            VALUES (?, ?, ?, ?, 384, ?, ?::FLOAT[384], TRUE)
            """,
            [
                f"embedding_{chunk_id}",
                chunk_id,
                MODEL_NAME,
                MODEL_REVISION,
                chunk_id.ljust(64, "0")[:64],
                vector,
            ],
        )

    def test_fusion_prioritizes_agreement_and_explains_scores(self) -> None:
        results = hybrid_search(
            self.connection,
            "spinodal pair",
            query_embedding=self._vector(1.0, 0.0),
            limit=3,
            candidate_pool=4,
        )
        self.assertEqual(results[0].chunk_id, "chunk_both")
        self.assertEqual(results[0].retrieval_channels, "lexical+semantic")
        self.assertIsNotNone(results[0].lexical_rank)
        self.assertIsNotNone(results[0].semantic_rank)
        self.assertEqual(results[0].citation, "Primary study, p. 4")

    def test_reference_noise_is_removed_and_semantic_only_can_survive(self) -> None:
        results = hybrid_search(
            self.connection,
            "spinodal pair",
            query_embedding=self._vector(1.0, 0.0),
            limit=3,
            candidate_pool=4,
        )
        ids = {result.chunk_id for result in results}
        self.assertNotIn("chunk_reference", ids)
        self.assertIn("chunk_semantic", ids)
        semantic = next(
            result for result in results
            if result.chunk_id == "chunk_semantic"
        )
        self.assertEqual(semantic.retrieval_channels, "semantic")

    def test_requested_system_is_an_explainable_relevance_signal(self) -> None:
        results = hybrid_search(
            self.connection,
            "spinodal pair",
            query_embedding=self._vector(1.0, 0.0),
            system_name="Mo-Nb-Ta-W",
            limit=3,
            candidate_pool=4,
        )
        matched = next(
            result for result in results
            if result.chunk_id == "chunk_semantic"
        )
        self.assertTrue(matched.system_entity_match)
        self.assertEqual(matched.requested_system, "Mo-Nb-Ta-W")
        self.assertGreater(matched.system_entity_weight, 1.0)


if __name__ == "__main__":
    unittest.main()
