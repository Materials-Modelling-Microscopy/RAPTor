from types import SimpleNamespace
import unittest

import numpy as np

from alloy_web.adapters.alloy_summary_adapter import (
    _classify_equilibrium,
    generate_simplex_grid,
)


def _equilibrium(phases, fractions):
    return SimpleNamespace(
        Phase=SimpleNamespace(values=np.asarray(phases, dtype=object)),
        NP=SimpleNamespace(values=np.asarray(fractions, dtype=float)),
    )


class MiscibilityClassificationTests(unittest.TestCase):
    def test_two_bcc_composition_sets_are_not_single_phase(self):
        result = _classify_equilibrium(
            _equilibrium(["BCC_A2", "BCC_A2"], [0.55, 0.45]),
            threshold=0.99,
        )

        self.assertFalse(result[0])
        self.assertEqual(result[3], ["BCC_A2", "BCC_A2"])

    def test_one_solid_solution_vertex_above_threshold_is_miscible(self):
        result = _classify_equilibrium(
            _equilibrium(["BCC_A2", ""], [0.995, np.nan]),
            threshold=0.99,
        )

        self.assertTrue(result[0])
        self.assertEqual(result[1], "BCC_A2")

    def test_second_active_phase_prevents_miscible_classification(self):
        result = _classify_equilibrium(
            _equilibrium(["BCC_A2", "CR1W1_MP"], [0.99999, 0.00001]),
            threshold=0.99,
        )

        self.assertFalse(result[0])


class SimplexGridTests(unittest.TestCase):
    def test_grids_are_normalized_and_capped_at_400_points(self):
        expected_counts = {2: 400, 3: 378, 4: 364, 5: 330}

        for components, expected_count in expected_counts.items():
            with self.subTest(components=components):
                grid = generate_simplex_grid(components, max_points=400)
                self.assertEqual(len(grid), expected_count)
                self.assertLessEqual(len(grid), 400)
                np.testing.assert_allclose(grid.sum(axis=1), 1.0)


if __name__ == "__main__":
    unittest.main()
