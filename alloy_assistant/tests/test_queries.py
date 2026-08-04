"""Tests for the reviewed read-only SQL query layer."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.ingest_binary_equimolar import (
    ingest_binary_equimolar,
)
from alloy_assistant.src.queries import (
    canonicalize_binary_system,
    find_binaries_above_miscibility_temperature,
    find_room_temperature_stable_binaries,
    get_binary_system_summary,
    get_database_summary,
    rank_binary_pairs_by_hmix,
)


class QueryLayerTest(unittest.TestCase):
    """Exercise queries against a fresh, reproducible in-memory database."""

    def setUp(self) -> None:
        self.connection_manager = connect(":memory:")
        self.connection = self.connection_manager.__enter__()
        initialize_schema(self.connection)
        ingest_binary_equimolar(self.connection)

    def tearDown(self) -> None:
        self.connection_manager.__exit__(None, None, None)

    def test_database_summary(self) -> None:
        summary = get_database_summary(self.connection)
        self.assertEqual(summary.sources, 1)
        self.assertEqual(summary.elements, 9)
        self.assertEqual(summary.alloy_systems, 36)
        self.assertEqual(summary.compositions, 36)
        self.assertEqual(summary.pairwise_interactions, 36)
        self.assertEqual(summary.calculation_runs, 36)
        self.assertEqual(summary.miscibility_predictions, 36)
        self.assertEqual(summary.pmr_predictions, 0)
        self.assertEqual(summary.experimental_samples, 0)
        self.assertEqual(summary.thermodynamic_databases, 0)
        self.assertEqual(summary.documents, 0)
        self.assertEqual(summary.document_chunks, 0)
        self.assertEqual(summary.chunk_entities, 0)

    def test_system_lookup_is_canonicalized_and_parameterized(self) -> None:
        result = get_binary_system_summary(self.connection, "Hf-Cr")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.canonical_name, "Cr-Hf")
        self.assertAlmostEqual(result.hmix_eV_atom, 0.657)
        self.assertEqual(result.miscibility_temperature_K, 3900.0)

    def test_hmix_ranking(self) -> None:
        highest = rank_binary_pairs_by_hmix(self.connection, limit=1)
        self.assertEqual(highest[0].canonical_name, "Cr-Zr")
        self.assertAlmostEqual(highest[0].hmix_eV_atom, 1.0666)

    def test_room_temperature_and_threshold_filters(self) -> None:
        room_temperature = find_room_temperature_stable_binaries(
            self.connection
        )
        self.assertEqual(len(room_temperature), 8)
        self.assertIn("Nb-Ta", {row.canonical_name for row in room_temperature})
        self.assertIn("Ta-W", {row.canonical_name for row in room_temperature})

        high = find_binaries_above_miscibility_temperature(
            self.connection,
            3500,
        )
        self.assertTrue(high)
        self.assertTrue(
            all(row.miscibility_temperature_K >= 3500 for row in high)
        )

    def test_input_validation(self) -> None:
        self.assertEqual(canonicalize_binary_system(" Hf-Cr "), "Cr-Hf")
        with self.assertRaises(ValueError):
            canonicalize_binary_system("Cr")
        with self.assertRaises(ValueError):
            rank_binary_pairs_by_hmix(self.connection, limit=0)


if __name__ == "__main__":
    unittest.main()
