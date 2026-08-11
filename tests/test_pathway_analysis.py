import unittest

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from alloy_web.config import TDB_DIR
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.pathway_analysis import (
    _integrated_burden,
    _sample_path,
    analyze_processing_paths,
    generate_processing_paths,
    plot_path_energy_profiles,
    plot_path_phase_fractions,
    plot_system_path_burden_landscape,
)


class PathGenerationTests(unittest.TestCase):
    def test_quaternary_orders_collapse_to_twelve_thermodynamic_paths(self):
        paths = generate_processing_paths(
            {"CR": 0.25, "MO": 0.25, "NB": 0.25, "TI": 0.25}
        )

        self.assertEqual(len(paths), 12)
        self.assertTrue(
            all(len(path["equivalent_orders"]) == 2 for path in paths)
        )
        self.assertTrue(
            all(len(path["subset_sequence"]) == 3 for path in paths)
        )

    def test_sampling_gives_equal_stage_intervals(self):
        elements = ["CR", "MO", "NB", "TI"]
        nodes = [
            {"CR": 0.5, "MO": 0.5},
            {"CR": 1 / 3, "MO": 1 / 3, "NB": 1 / 3},
            {element: 0.25 for element in elements},
        ]

        samples = _sample_path(nodes, elements, points_per_segment=3)
        coordinates = [sample["path_coordinate"] for sample in samples]

        np.testing.assert_allclose(coordinates, [0.0, 0.25, 0.5, 0.75, 1.0])
        np.testing.assert_allclose(
            samples[2]["composition"],
            [1 / 3, 1 / 3, 1 / 3, 0.0],
        )
        for sample in samples:
            self.assertAlmostEqual(float(sample["composition"].sum()), 1.0)

    def test_integrated_burden_uses_normalized_path_coordinate(self):
        burden = _integrated_burden(
            np.asarray([0.0, 0.5, 1.0]),
            np.asarray([0.0, 10.0, 0.0]),
        )

        self.assertEqual(burden, 5.0)


class PathwayCalculationTests(unittest.TestCase):
    def test_ternary_analysis_returns_paths_phases_and_two_system_metrics(self):
        result = analyze_processing_paths(
            tdb_path=TDB_DIR / "Cr-Mo-Ti.tdb",
            target_composition={"CR": 1 / 3, "MO": 1 / 3, "TI": 1 / 3},
            temperature=1500.0,
            points_per_segment=2,
        )

        paths = result["paths"]
        self.assertEqual(len(paths), 3)
        self.assertTrue(
            (paths["integrated_burden_meV_per_atom"] >= 0.0).all()
        )

        metrics = result["system_metrics"]
        self.assertEqual(
            set(metrics),
            {
                "mean_integrated_burden_meV_per_atom",
                "path_dependence_variance_meV2_per_atom2",
            },
        )
        np.testing.assert_allclose(
            metrics["mean_integrated_burden_meV_per_atom"],
            paths["integrated_burden_meV_per_atom"].mean(),
        )
        np.testing.assert_allclose(
            metrics["path_dependence_variance_meV2_per_atom2"],
            paths["integrated_burden_meV_per_atom"].var(ddof=0),
        )

        fractions = result["phase_fractions"]
        fraction_sums = fractions.groupby(
            ["path_id", "path_coordinate"]
        )["phase_fraction"].sum()
        np.testing.assert_allclose(fraction_sums, 1.0)


class PathwayPlotTests(unittest.TestCase):
    def test_energy_and_phase_fraction_plots_use_tabular_outputs(self):
        path_points = pd.DataFrame(
            {
                "path_id": [0, 0, 0],
                "path": ["A-B → A-B-C"] * 3,
                "path_coordinate": [0.0, 0.5, 1.0],
                "energy_above_hull_meV_per_atom": [0.0, 10.0, 2.0],
            }
        )
        phase_fractions = pd.DataFrame(
            {
                "path_id": [0, 0, 0, 0],
                "path": ["A-B → A-B-C"] * 4,
                "path_coordinate": [0.0, 0.5, 0.5, 1.0],
                "phase_label": ["BCC_A2", "BCC_A2", "LAVES", "BCC_A2"],
                "phase_fraction": [1.0, 0.6, 0.4, 1.0],
            }
        )

        energy_figure = plot_path_energy_profiles(path_points, path_ids=[0])
        phase_figure = plot_path_phase_fractions(phase_fractions, path_id=0)
        self.addCleanup(plt.close, energy_figure)
        self.addCleanup(plt.close, phase_figure)

        self.assertEqual(len(energy_figure.axes[0].lines), 1)
        self.assertEqual(phase_figure.axes[0].get_ylim(), (0.0, 1.0))
        self.assertEqual(len(phase_figure.axes[0].collections), 2)
        self.assertEqual(len(phase_figure.axes[0].patches), 0)

    def test_inter_system_landscape_is_a_non_directional_scatter(self):
        metrics = pd.DataFrame(
            {
                "System": ["A-B-C", "A-B-D", "A-C-D"],
                "mean_integrated_burden_meV_per_atom": [2.0, 8.0, 5.0],
                "path_dependence_variance_meV2_per_atom2": [1.0, 4.0, 9.0],
            }
        )

        figure = plot_system_path_burden_landscape(metrics)
        self.addCleanup(plt.close, figure)

        axis = figure.axes[0]
        self.assertEqual(len(axis.collections), 1)
        self.assertEqual(len(axis.texts), 3)
        self.assertNotIn("better", axis.get_xlabel().lower())
        self.assertNotIn("better", axis.get_ylabel().lower())


if __name__ == "__main__":
    unittest.main()
