import unittest

from alloy_web.adapters.pathway_adapter import run_pathway_analysis
from alloy_web.config import TDB_DIR


class PathwayAdapterTests(unittest.TestCase):
    def test_adapter_returns_compact_pathway_result(self):
        result = run_pathway_analysis(
            alloy_system=["Cr", "Mo", "Ti"],
            mol_ratio=[1 / 3, 1 / 3, 1 / 3],
            temperature=1500.0,
            tdb_dir=TDB_DIR,
            points_per_segment=2,
        )

        self.assertEqual(result.alloy_system, ["Cr", "Mo", "Ti"])
        self.assertEqual(len(result.paths), 3)
        self.assertEqual(result.starting_binaries, ["CR-MO", "CR-TI", "MO-TI"])
        self.assertGreaterEqual(result.mean_integrated_burden, 0.0)
        self.assertGreaterEqual(result.path_dependence_variance, 0.0)

        for starting_binary in result.starting_binaries:
            self.assertEqual(
                len(result.path_ids_for_starting_binary(starting_binary)),
                1,
            )

    def test_adapter_rejects_non_normalized_composition(self):
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            run_pathway_analysis(
                alloy_system=["Cr", "Mo", "Ti"],
                mol_ratio=[0.3, 0.3, 0.3],
                temperature=1500.0,
                tdb_dir=TDB_DIR,
                points_per_segment=2,
            )


if __name__ == "__main__":
    unittest.main()
