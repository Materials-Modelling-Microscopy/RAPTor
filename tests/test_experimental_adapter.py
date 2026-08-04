from pathlib import Path
import tempfile
import unittest

from alloy_assistant.src.database import DEFAULT_DATABASE_PATH
from alloy_web.adapters.experimental_adapter import (
    DEFAULT_CITATION_PATH,
    _reference_for_source_row,
    load_citation_catalog,
    load_experimental_evidence,
)


class ExperimentalCitationCatalogTests(unittest.TestCase):
    def test_catalog_maps_every_manuscript_record_and_reference(self):
        catalog = load_citation_catalog()

        self.assertEqual(len(catalog["reference_numbers"]), 109)
        self.assertEqual(set(catalog["references"]), {str(i) for i in range(1, 55)})
        self.assertEqual(_reference_for_source_row(3, catalog), 1)
        self.assertEqual(_reference_for_source_row(5, catalog), 3)
        self.assertEqual(_reference_for_source_row(111, catalog), 54)

    def test_out_of_range_source_row_is_rejected_instead_of_miscited(self):
        catalog = load_citation_catalog()

        with self.assertRaisesRegex(ValueError, "no manuscript citation mapping"):
            _reference_for_source_row(112, catalog)

    def test_invalid_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_path = Path(directory) / "invalid.json"
            invalid_path.write_text(
                '{"first_source_row": 3, "reference_numbers": [], "references": {}}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "all 109 records"):
                load_citation_catalog(invalid_path)


@unittest.skipUnless(DEFAULT_DATABASE_PATH.is_file(), "Alloy Assistant DB unavailable")
class ExperimentalEvidenceIntegrationTests(unittest.TestCase):
    def test_cr_mo_ta_ti_records_keep_their_distinct_citations(self):
        evidence = load_experimental_evidence(["Cr", "Mo", "Ta", "Ti"])

        records = evidence.observations.to_dict("records")
        self.assertEqual(len(records), 2)
        self.assertEqual(
            records[0],
            {
                "Composition": "CrMoTaTi",
                "Reported phases": "BCC",
                "Processing method": "Cast",
                "Processing temperature (K)": 2576.0,
                "Reference": "[3]",
            },
        )
        self.assertEqual(records[1]["Reported phases"], "BCC+Laves")
        self.assertEqual(records[1]["Processing method"], "Anneal")
        self.assertEqual(records[1]["Reference"], "[1]")
        self.assertEqual(evidence.citations["Reference"].tolist(), ["[1]", "[3]"])

    def test_unlisted_exact_system_returns_no_evidence(self):
        evidence = load_experimental_evidence(["Cr", "Ta", "Ti", "W"])

        self.assertTrue(evidence.database_available)
        self.assertTrue(evidence.observations.empty)
        self.assertTrue(evidence.citations.empty)

    def test_missing_database_is_nonfatal(self):
        evidence = load_experimental_evidence(
            ["Cr", "Mo", "Ta", "Ti"],
            database_path=Path("does-not-exist.duckdb"),
            citation_path=DEFAULT_CITATION_PATH,
        )

        self.assertFalse(evidence.database_available)
        self.assertTrue(evidence.observations.empty)


if __name__ == "__main__":
    unittest.main()
