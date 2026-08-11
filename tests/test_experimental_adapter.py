from pathlib import Path
import tempfile
import unittest

from alloy_assistant.src.database import DEFAULT_DATABASE_PATH
from alloy_web.adapters.experimental_adapter import (
    DEFAULT_CITATION_PATH,
    DEFAULT_EXPERIMENTAL_SOURCE_PATH,
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


class ExperimentalEvidenceIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(DEFAULT_DATABASE_PATH.is_file(), "Alloy Assistant DB unavailable")
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

    @unittest.skipUnless(DEFAULT_DATABASE_PATH.is_file(), "Alloy Assistant DB unavailable")
    def test_unlisted_exact_system_returns_no_evidence(self):
        evidence = load_experimental_evidence(["Cr", "Ta", "Ti", "W"])

        self.assertTrue(evidence.database_available)
        self.assertTrue(evidence.observations.empty)
        self.assertTrue(evidence.citations.empty)

    def test_missing_database_uses_reviewed_source_file(self):
        evidence = load_experimental_evidence(
            ["Cr", "Mo", "Ta", "Ti"],
            database_path=Path("does-not-exist.duckdb"),
            citation_path=DEFAULT_CITATION_PATH,
            source_path=DEFAULT_EXPERIMENTAL_SOURCE_PATH,
        )

        self.assertFalse(evidence.database_available)
        self.assertEqual(len(evidence.observations), 2)
        self.assertEqual(evidence.observations["Reference"].tolist(), ["[3]", "[1]"])

    def test_missing_database_and_source_are_nonfatal(self):
        evidence = load_experimental_evidence(
            ["Cr", "Mo", "Ta", "Ti"],
            database_path=Path("does-not-exist.duckdb"),
            citation_path=DEFAULT_CITATION_PATH,
            source_path=Path("does-not-exist.csv"),
        )

        self.assertFalse(evidence.database_available)
        self.assertTrue(evidence.observations.empty)


if __name__ == "__main__":
    unittest.main()
