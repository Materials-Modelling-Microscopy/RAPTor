from __future__ import annotations

import inspect
from pathlib import Path
import unittest

import raptor_alloys as rap


ROOT = Path(__file__).resolve().parents[1]
API_REFERENCE = ROOT / "docs" / "reference" / "api.md"
RESULT_REFERENCE = ROOT / "docs" / "reference" / "results.md"
GUIDES = [
    "phase-stability.md",
    "phase-diagrams.md",
    "spinodal.md",
    "symplex.md",
    "pathways.md",
    "system-screening.md",
]


class PublicApiDocumentationTests(unittest.TestCase):
    def test_every_public_function_has_reference_entry_and_structured_docstring(self):
        reference = API_REFERENCE.read_text(encoding="utf-8")
        functions = [
            name for name in rap.__all__
            if name.startswith("run_") and inspect.isfunction(getattr(rap, name))
        ]
        self.assertEqual(8, len(functions))
        for name in functions:
            with self.subTest(name=name):
                self.assertIn(f"`raptor_alloys.{name}`", reference)
                docstring = inspect.getdoc(getattr(rap, name)) or ""
                self.assertIn("Args:", docstring)
                self.assertIn("Returns:", docstring)
                self.assertIn("Raises:", docstring)

    def test_every_public_result_type_has_reference_entry_and_docstring(self):
        reference = RESULT_REFERENCE.read_text(encoding="utf-8")
        result_types = [
            name for name in rap.__all__
            if name.endswith("Result") and inspect.isclass(getattr(rap, name))
        ]
        self.assertEqual(9, len(result_types))
        for name in result_types:
            with self.subTest(name=name):
                self.assertIn(f"`raptor_alloys.{name}`", reference)
                self.assertTrue(inspect.getdoc(getattr(rap, name)))

    def test_every_calculation_guide_shows_representative_output(self):
        for filename in GUIDES:
            with self.subTest(filename=filename):
                guide = (ROOT / "docs" / "guides" / filename).read_text(
                    encoding="utf-8"
                )
                self.assertIn("## Representative", guide)
                self.assertTrue("assets/outputs/" in guide or "| ---" in guide)

    def test_representative_output_assets_exist(self):
        required = [
            "phase-stability.png",
            "phase-stability-energy.png",
            "phase-diagram.png",
            "composition-splitting-1000K.png",
            "composition-splitting-1800K.png",
            "spinodal-spectrum.png",
            "spinodal-mode.png",
            "symplex.png",
            "pathways.csv",
            "system-summary.csv",
            "system-comparison.csv",
        ]
        output_dir = ROOT / "docs" / "assets" / "outputs"
        for filename in required:
            with self.subTest(filename=filename):
                path = output_dir / filename
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
