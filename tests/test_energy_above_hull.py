import unittest

import matplotlib.pyplot as plt
import numpy as np

from alloy_web.adapters.phasefield_adapter import (
    run_phase_fraction_temperature_prediction,
)
from alloy_web.config import TDB_DIR
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.energy_above_hull import (
    energy_above_hull_mev,
    first_temperature_at_or_below,
)


class EnergyAboveHullUnitTests(unittest.TestCase):
    def test_energy_conversion_and_non_negative_bound(self):
        values = energy_above_hull_mev(
            np.asarray([96.485, -10.0]),
            np.asarray([0.0, 0.0]),
        )

        np.testing.assert_allclose(values, [1.0, 0.0])

    def test_threshold_temperature_is_linearly_interpolated(self):
        temperature = first_temperature_at_or_below(
            np.asarray([1000.0, 1100.0]),
            np.asarray([60.0, 40.0]),
            threshold=50.0,
        )

        self.assertEqual(temperature, 1050.0)


class PhaseFractionEnergyIntegrationTests(unittest.TestCase):
    def test_bcc_energy_curve_uses_composition_and_leaves_tdb_unchanged(self):
        tdb_path = TDB_DIR / "Cr-W.tdb"
        original_mtime = tdb_path.stat().st_mtime_ns

        result = run_phase_fraction_temperature_prediction(
            alloy_system=["Cr", "W"],
            mol_ratio=[0.5, 0.5],
            temperature_min=300.0,
            temperature_max=3000.0,
            temperature_step=100.0,
            tdb_dir=TDB_DIR,
        )
        self.addCleanup(plt.close, result.figure)
        self.addCleanup(plt.close, result.energy_above_hull_figure)

        energies = result.energy_above_hull_data[
            "BCC_A2 energy above hull (meV/atom)"
        ]
        self.assertTrue((energies >= 0.0).all())
        self.assertGreater(energies.iloc[0], 50.0)
        self.assertAlmostEqual(energies.iloc[-1], 0.0, places=6)
        self.assertIsNotNone(result.metastable_temperature)
        self.assertIsNotNone(result.stable_temperature)

        alternate = run_phase_fraction_temperature_prediction(
            alloy_system=["Cr", "W"],
            mol_ratio=[0.4, 0.6],
            temperature_min=300.0,
            temperature_max=500.0,
            temperature_step=100.0,
            tdb_dir=TDB_DIR,
        )
        self.addCleanup(plt.close, alternate.figure)
        self.addCleanup(plt.close, alternate.energy_above_hull_figure)
        alternate_energy = alternate.energy_above_hull_data[
            "BCC_A2 energy above hull (meV/atom)"
        ].iloc[0]
        self.assertNotAlmostEqual(energies.iloc[0], alternate_energy, places=6)
        self.assertEqual(original_mtime, tdb_path.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
