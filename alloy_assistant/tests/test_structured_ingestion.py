"""End-to-end tests for the structured-data ingestion pipeline."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.ingest_all_structured import ingest_all_structured
from alloy_assistant.src.queries import (
    canonicalize_system,
    find_pmr_candidates,
    get_experimental_observations_for_system,
    get_miscibility_predictions_for_system,
    get_pairwise_interactions_for_system,
    get_pmr_for_system,
    get_predicted_phases_for_system,
    get_system_overview,
    get_tdb_coverage,
    rank_equimolar_miscibility_predictions,
)


class StructuredIngestionTest(unittest.TestCase):
    """Load every reviewed structured source into an in-memory database."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.connection_manager = connect(":memory:")
        cls.connection = cls.connection_manager.__enter__()
        initialize_schema(cls.connection)
        cls.first_report = ingest_all_structured(cls.connection)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection_manager.__exit__(None, None, None)

    def test_expected_curated_counts(self) -> None:
        totals = self.first_report["database_totals"]
        self.assertEqual(totals["sources"], 465)
        self.assertEqual(totals["elements"], 9)
        self.assertEqual(totals["alloy_systems"], 457)
        self.assertEqual(totals["compositions"], 419)
        self.assertEqual(totals["pairwise_interactions"], 36)
        self.assertEqual(totals["calculation_runs"], 853)
        self.assertEqual(totals["miscibility_predictions"], 481)
        self.assertEqual(totals["pmr_predictions"], 1116)
        self.assertEqual(totals["predicted_phase_fractions"], 800)
        self.assertEqual(totals["experimental_samples"], 109)
        self.assertEqual(totals["processing_events"], 109)
        self.assertEqual(totals["experimental_phase_observations"], 109)
        self.assertEqual(totals["thermodynamic_databases"], 456)

    def test_validation_preserves_source_rows(self) -> None:
        report = self.first_report["experimental_validation"]
        self.assertEqual(report["staged_rows"], 111)
        self.assertEqual(report["substantive_rows"], 109)
        self.assertEqual(report["samples"], 109)

    def test_system_coverage(self) -> None:
        by_size = dict(
            self.connection.execute(
                """
                SELECT component_count, count(*)
                FROM (
                    SELECT
                        system_id,
                        count(*) AS component_count
                    FROM alloy.alloy_system_elements
                    GROUP BY system_id
                )
                GROUP BY component_count
                ORDER BY component_count
                """
            ).fetchall()
        )
        self.assertEqual(
            by_size,
            {2: 36, 3: 84, 4: 126, 5: 126, 6: 84, 7: 1},
        )

    def test_full_pipeline_is_idempotent(self) -> None:
        second_report = ingest_all_structured(self.connection)
        self.assertEqual(
            second_report["database_totals"],
            self.first_report["database_totals"],
        )
        self.assertTrue(second_report["binary_equimolar"]["already_ingested"])
        self.assertEqual(
            second_report["higher_order_equimolar"]["files_ingested"],
            0,
        )
        self.assertEqual(second_report["pmr"]["files_ingested"], 0)
        self.assertTrue(
            second_report["experimental_validation"]["already_ingested"]
        )
        self.assertEqual(
            second_report["tdb_registry"]["files_registered"],
            0,
        )

    def test_general_system_overview(self) -> None:
        self.assertEqual(
            canonicalize_system(" W-Ta-Nb-Mo "),
            "Mo-Nb-Ta-W",
        )
        overview = get_system_overview(
            self.connection,
            "W-Ta-Nb-Mo",
        )
        self.assertIsNotNone(overview)
        assert overview is not None
        self.assertEqual(overview.n_components, 4)
        self.assertEqual(overview.miscibility_prediction_count, 4)
        self.assertEqual(overview.pmr_prediction_count, 3)
        self.assertEqual(overview.experimental_sample_count, 3)
        self.assertTrue(overview.has_thermodynamic_database)

    def test_miscibility_and_pmr_queries(self) -> None:
        predictions = get_miscibility_predictions_for_system(
            self.connection,
            "Mo-Nb-Ta-W",
        )
        self.assertEqual(len(predictions), 4)
        curated = [
            row for row in predictions if row.quality_flag == "validated"
        ]
        self.assertEqual(len(curated), 1)
        self.assertEqual(curated[0].miscibility_temperature_K, 300.0)
        self.assertEqual(curated[0].melting_temperature_K, 3157.75)
        self.assertIn(
            "lower values are more favorable",
            curated[0].miscibility_ratio_definition,
        )

        pmr = get_pmr_for_system(
            self.connection,
            "Mo-Nb-Ta-W",
            temperature_K=1000,
        )
        self.assertEqual(len(pmr), 1)
        self.assertEqual(pmr[0].pmr_percent, 100.0)
        self.assertEqual(pmr[0].grid_spacing_atomic_fraction, 0.1)

    def test_multicomponent_pairwise_interaction_profile(self) -> None:
        interactions = get_pairwise_interactions_for_system(
            self.connection,
            "Ta-V-W-Zr",
        )
        self.assertEqual(len(interactions), 6)
        self.assertEqual(
            {row.canonical_pair for row in interactions},
            {
                "Ta-V",
                "Ta-W",
                "Ta-Zr",
                "V-W",
                "V-Zr",
                "W-Zr",
            },
        )
        self.assertTrue(
            all(row.requested_system == "Ta-V-W-Zr" for row in interactions)
        )

    def test_mid_pmr_candidate_discovery_by_component_count(self) -> None:
        candidates = find_pmr_candidates(
            self.connection,
            n_components=4,
            target_pmr_percent=50,
            tolerance_percent=25,
            limit=8,
        )
        self.assertTrue(candidates)
        self.assertLessEqual(len(candidates), 8)
        self.assertTrue(all(row.n_components == 4 for row in candidates))
        self.assertTrue(
            all(25 <= row.pmr_percent <= 75 for row in candidates)
        )
        self.assertEqual(
            len({row.canonical_name for row in candidates}),
            len(candidates),
        )

    def test_phase_and_experimental_queries_preserve_meaning(self) -> None:
        predicted = get_predicted_phases_for_system(
            self.connection,
            "Mo-Nb-Ta-W",
            temperature_K=300,
        )
        self.assertEqual(
            {row.phase_name for row in predicted},
            {"BCC_A2", "TA1W3_MP"},
        )
        observed = get_experimental_observations_for_system(
            self.connection,
            "Mo-Nb-Ta-W",
        )
        self.assertEqual(len(observed), 3)
        self.assertEqual(
            {row.processing_route for row in observed},
            {"Cast", "AM"},
        )
        self.assertEqual(
            {row.raw_phase_label for row in observed},
            {"BCC"},
        )

    def test_tdb_coverage_distinguishes_missing_from_unknown_system(self) -> None:
        covered = get_tdb_coverage(self.connection, "Mo-Nb-Ta-W")
        self.assertIsNotNone(covered)
        assert covered is not None
        self.assertTrue(covered.has_database)
        self.assertEqual(covered.phase_count, 12)
        self.assertEqual(covered.parameter_count, 51)

        uncovered = get_tdb_coverage(
            self.connection,
            "Hf-Mo-Nb-Ta-Ti-W-Zr",
        )
        self.assertIsNotNone(uncovered)
        assert uncovered is not None
        self.assertFalse(uncovered.has_database)
        self.assertIsNone(
            get_tdb_coverage(
                self.connection,
                "Cr-Hf-Mo-Nb-Ta-Ti-Zr",
            )
        )

    def test_ranked_miscibility_query(self) -> None:
        ranked = rank_equimolar_miscibility_predictions(
            self.connection,
            limit=3,
            n_components=4,
        )
        self.assertEqual(len(ranked), 3)
        self.assertTrue(all(row.is_equimolar for row in ranked))
        self.assertTrue(
            all(row.canonical_name.count("-") == 3 for row in ranked)
        )
        self.assertEqual(ranked[0].miscibility_temperature_K, 3900.0)


if __name__ == "__main__":
    unittest.main()
