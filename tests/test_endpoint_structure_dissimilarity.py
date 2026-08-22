from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EUTECTICS = ROOT / "eutectics"
if str(EUTECTICS) not in sys.path:
    sys.path.insert(0, str(EUTECTICS))

from analyze_endpoint_structure_dissimilarity import (  # noqa: E402
    load_analysis_data,
    relation_summary,
)


class EndpointStructureDissimilarityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_analysis_data(
            EUTECTICS / "results" / "validated" / "validated_annotation_joined.csv",
            EUTECTICS / "data" / "element_endpoint_structures.csv",
        )

    def test_every_completed_system_has_two_endpoint_prototypes(self):
        self.assertEqual(len(self.data), 433)
        self.assertFalse(self.data["endpoint_a_prototype"].isna().any())
        self.assertFalse(self.data["endpoint_b_prototype"].isna().any())
        self.assertEqual(set(self.data["d_s"]), {0, 1})

    def test_primary_descriptor_has_expected_class_counts(self):
        table = self.data.groupby("d_s")["is_eutectic"].agg(["size", "sum"])
        self.assertEqual(tuple(table.loc[0]), (113, 49))
        self.assertEqual(tuple(table.loc[1]), (320, 290))

    def test_finer_structure_relation_is_auditable(self):
        summary = relation_summary(self.data).set_index("structure_relation")
        self.assertEqual(int(summary.loc["same_prototype", "systems"]), 113)
        self.assertEqual(
            int(summary.loc["same_bravais_different_basis", "systems"]), 19
        )
        self.assertEqual(int(summary.loc["different_bravais", "systems"]), 301)

    def test_representative_pair_assignments(self):
        rows = self.data.set_index("pair")
        self.assertEqual(int(rows.loc["Ag-Au", "d_s"]), 0)
        self.assertEqual(rows.loc["Ag-Si", "structure_relation"], "same_bravais_different_basis")
        self.assertEqual(int(rows.loc["Nb-Ta", "d_s"]), 0)
        self.assertEqual(rows.loc["Al-Ga", "structure_relation"], "different_bravais")


if __name__ == "__main__":
    unittest.main()
