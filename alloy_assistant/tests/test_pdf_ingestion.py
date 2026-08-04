"""Tests for the prototype PDF chunking and retrieval pipeline."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.ingest_pdf_documents import (
    chunk_page_text,
    ingest_pdf_documents,
)
from alloy_assistant.src.queries import (
    get_database_summary,
    list_documents,
    search_document_chunks,
)


class PdfIngestionTest(unittest.TestCase):
    """Exercise all current PDFs in an isolated in-memory database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection_manager = connect(":memory:")
        cls.connection = cls.connection_manager.__enter__()
        initialize_schema(cls.connection)
        cls.first_report = ingest_pdf_documents(cls.connection)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection_manager.__exit__(None, None, None)

    def test_chunker_respects_limits_and_overlap(self) -> None:
        text = " ".join(
            f"Sentence {index} has several useful scientific words."
            for index in range(30)
        )
        chunks = chunk_page_text(text, max_words=50, overlap_words=10)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.split()) <= 60 for chunk in chunks))
        self.assertIn(
            "Sentence 6",
            chunks[0] + chunks[1],
        )

    def test_all_pdfs_are_registered_and_chunked(self) -> None:
        report = self.first_report
        self.assertEqual(report.files_discovered, 11)
        self.assertEqual(report.files_registered, 11)
        self.assertEqual(report.documents, 11)
        self.assertEqual(report.pages, 412)
        self.assertGreater(report.chunks, report.pages)
        self.assertGreater(report.entity_annotations, report.chunks)

        documents = list_documents(self.connection)
        self.assertEqual(len(documents), 11)
        self.assertEqual(sum(doc.page_count for doc in documents), 412)
        self.assertTrue(all(doc.chunk_count > 0 for doc in documents))

    def test_evidence_classes_are_automatic(self) -> None:
        counts = dict(
            self.connection.execute(
                """
                SELECT source_class, count(*)
                FROM alloy.sources
                GROUP BY source_class
                """
            ).fetchall()
        )
        self.assertEqual(
            counts,
            {
                "dissertation": 1,
                "external_literature": 5,
                "manuscript": 4,
                "own_publication": 1,
            },
        )

    def test_lexical_retrieval_returns_citable_chunks(self) -> None:
        results = search_document_chunks(
            self.connection,
            "spinodal decomposition",
            limit=5,
        )
        self.assertEqual(len(results), 5)
        self.assertTrue(all(result.page_start > 0 for result in results))
        self.assertTrue(
            all(
                "spinodal" in result.chunk_text.lower()
                or "decomposition" in result.chunk_text.lower()
                for result in results
            )
        )
        self.assertTrue(any(row.lexical_score == 2 for row in results))

    def test_pdf_ingestion_is_idempotent(self) -> None:
        second = ingest_pdf_documents(self.connection)
        self.assertEqual(second.files_registered, 0)
        self.assertEqual(second.files_already_registered, 11)
        self.assertEqual(second.chunks, self.first_report.chunks)
        self.assertEqual(
            get_database_summary(self.connection).documents,
            11,
        )


if __name__ == "__main__":
    unittest.main()
