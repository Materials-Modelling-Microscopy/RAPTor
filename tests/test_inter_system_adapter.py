from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from alloy_web.adapters.inter_system_adapter import (
    ACTIVE_PHASE_COUNT,
    MEAN_PATH_BURDEN,
    METRICS,
    MISCIBILITY_TEMPERATURE,
    PMR,
    PATH_BURDEN_VARIANCE,
    SPINODAL_TEMPERATURE,
    _metastability_gap,
    generate_candidate_systems,
    pareto_optimal_mask,
    run_inter_system_comparison,
)
from alloy_web.config import ROOT, TDB_DIR


INTERACTION_DATA_PATH = (
    ROOT
    / "external"
    / "Rapid_Phase_Field_Prediction"
    / "input"
    / "spinodal"
    / "binary_interactions.json"
)


class CandidateGenerationTests(unittest.TestCase):
    def test_existing_generator_produces_each_fixed_order_system_once(self):
        systems = generate_candidate_systems(["Cr", "Mo", "Nb", "Ta", "W"], 4)

        self.assertEqual(len(systems), 5)
        self.assertEqual(len(set(systems)), 5)
        self.assertEqual(systems[0], ("Cr", "Mo", "Nb", "Ta"))
        self.assertEqual(systems[-1], ("Mo", "Nb", "Ta", "W"))


class ParetoTests(unittest.TestCase):
    def test_pareto_respects_each_metrics_favorable_direction(self):
        self.assertEqual(METRICS[MISCIBILITY_TEMPERATURE].favorable, "lower")
        self.assertEqual(METRICS[PMR].favorable, "higher")
        data = pd.DataFrame(
            {
                MISCIBILITY_TEMPERATURE: [1000.0, 1100.0, 900.0, None],
                PMR: [80.0, 70.0, 60.0, 100.0],
            }
        )

        mask = pareto_optimal_mask(data, [MISCIBILITY_TEMPERATURE, PMR])

        self.assertEqual(mask.tolist(), [True, False, True, False])

    def test_spinodal_has_no_universal_pareto_direction(self):
        self.assertEqual(METRICS[SPINODAL_TEMPERATURE].favorable, "context")

    def test_pathway_metrics_have_no_assumed_favorable_direction(self):
        self.assertEqual(METRICS[MEAN_PATH_BURDEN].favorable, "context")
        self.assertEqual(METRICS[PATH_BURDEN_VARIANCE].favorable, "context")

    def test_negative_metastability_gap_is_bounded_at_zero(self):
        self.assertEqual(_metastability_gap(1200.0, 1400.0), 0.0)
        self.assertEqual(_metastability_gap(1500.0, 1200.0), 300.0)


class CacheIntegrationTests(unittest.TestCase):
    def test_second_run_uses_sqlite_without_modifying_tdb(self):
        tdb_path = TDB_DIR / "Cr-W.tdb"
        tdb_mtime = tdb_path.stat().st_mtime_ns
        parameters = dict(
            element_pool=["Cr", "W"],
            order=2,
            selected_metrics=[ACTIVE_PHASE_COUNT],
            primary_metric=ACTIVE_PHASE_COUNT,
            reference_temperature=1500.0,
            temperature_min=300.0,
            temperature_max=3000.0,
            temperature_step=100.0,
            lattice="BCC_A2",
            tdb_dir=TDB_DIR,
            interaction_data_path=INTERACTION_DATA_PATH,
        )

        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "metrics.sqlite3"
            first = run_inter_system_comparison(cache_path=cache_path, **parameters)
            second = run_inter_system_comparison(cache_path=cache_path, **parameters)

            self.assertTrue(cache_path.exists())
            self.assertEqual(first.cache_misses, 1)
            self.assertEqual(first.equilibrium_calculations, 1)
            self.assertEqual(second.cache_hits, 1)
            self.assertEqual(second.equilibrium_calculations, 0)
            self.assertEqual(
                first.data[ACTIVE_PHASE_COUNT].tolist(),
                second.data[ACTIVE_PHASE_COUNT].tolist(),
            )
            self.assertEqual(tdb_mtime, tdb_path.stat().st_mtime_ns)

    def test_pathway_metric_pair_is_computed_once_and_cached(self):
        parameters = dict(
            element_pool=["Cr", "Mo", "Ti"],
            order=3,
            selected_metrics=[MEAN_PATH_BURDEN, PATH_BURDEN_VARIANCE],
            primary_metric=MEAN_PATH_BURDEN,
            reference_temperature=1500.0,
            temperature_min=300.0,
            temperature_max=3000.0,
            temperature_step=100.0,
            lattice="BCC_A2",
            tdb_dir=TDB_DIR,
            interaction_data_path=INTERACTION_DATA_PATH,
            pathway_points_per_segment=2,
        )

        with TemporaryDirectory() as directory:
            cache_path = Path(directory) / "pathway_metrics.sqlite3"
            first = run_inter_system_comparison(cache_path=cache_path, **parameters)
            second = run_inter_system_comparison(cache_path=cache_path, **parameters)

            self.assertEqual(first.cache_misses, 1)
            self.assertGreater(first.equilibrium_calculations, 0)
            self.assertEqual(second.cache_hits, 2)
            self.assertEqual(second.equilibrium_calculations, 0)
            self.assertTrue(first.data[MEAN_PATH_BURDEN].notna().all())
            self.assertTrue(first.data[PATH_BURDEN_VARIANCE].notna().all())
            self.assertTrue(first.data["Rank"].isna().all())


if __name__ == "__main__":
    unittest.main()
