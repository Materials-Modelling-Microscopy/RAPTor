"""End-to-end tests for the first structured-data ingestion."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.ingest_binary_equimolar import (
    ingest_binary_equimolar,
)


class BinaryEquimolarIngestionTest(unittest.TestCase):
    """Verify staging, curation, normalization, and idempotency."""

    def test_ingestion_is_complete_and_idempotent(self) -> None:
        with connect(":memory:") as connection:
            initialize_schema(connection)

            first = ingest_binary_equimolar(connection)
            second = ingest_binary_equimolar(connection)

            self.assertFalse(first.already_ingested)
            self.assertTrue(second.already_ingested)
            self.assertEqual(first.staged_rows, 36)
            self.assertEqual(first.elements, 9)
            self.assertEqual(first.alloy_systems, 36)
            self.assertEqual(first.compositions, 36)
            self.assertEqual(first.composition_components, 72)
            self.assertEqual(first.pairwise_interactions, 36)
            self.assertEqual(first.calculation_runs, 36)
            self.assertEqual(first.miscibility_predictions, 36)
            self.assertEqual(first.normalized_room_temperature_rows, 6)

            nb_ta = connection.execute(
                """
                SELECT
                    mp.reported_miscibility_temperature_K,
                    mp.miscibility_temperature_K,
                    mp.normalization_rule
                FROM alloy.miscibility_predictions AS mp
                JOIN alloy.compositions AS c USING (composition_id)
                JOIN alloy.alloy_systems AS s USING (system_id)
                WHERE s.canonical_name = 'Nb-Ta'
                """
            ).fetchone()
            self.assertEqual(nb_ta, (200.0, 200.0, "none"))

            cr_v = connection.execute(
                """
                SELECT
                    mp.reported_miscibility_temperature_K,
                    mp.miscibility_temperature_K,
                    mp.normalization_rule
                FROM alloy.miscibility_predictions AS mp
                JOIN alloy.compositions AS c USING (composition_id)
                JOIN alloy.alloy_systems AS s USING (system_id)
                WHERE s.canonical_name = 'Cr-V'
                """
            ).fetchone()
            self.assertEqual(
                cr_v,
                (0.0, 300.0, "zero_to_room_temperature"),
            )


if __name__ == "__main__":
    unittest.main()

