import unittest
from xml.etree import ElementTree

from alloy_web.icons import ICON_NAMES, brand_favicon, icon_markup, icon_path


class IconSystemTests(unittest.TestCase):
    def test_every_registered_icon_is_valid_svg(self):
        for name in ICON_NAMES:
            with self.subTest(icon=name):
                path = icon_path(name)
                self.assertTrue(path.exists())
                root = ElementTree.parse(path).getroot()
                self.assertTrue(root.tag.endswith("svg"))
                self.assertEqual(root.attrib["viewBox"], "0 0 24 24")

    def test_inline_markup_has_fixed_size_and_accessibility_attributes(self):
        markup = icon_markup("brand", size=32, class_name="test-icon")

        self.assertIn('width="32"', markup)
        self.assertIn('height="32"', markup)
        self.assertIn('class="test-icon"', markup)
        self.assertIn('aria-hidden="true"', markup)

    def test_brand_favicon_is_a_transparent_rgba_image(self):
        favicon = brand_favicon()

        self.assertEqual(favicon.mode, "RGBA")
        self.assertEqual(favicon.size, (64, 64))


if __name__ == "__main__":
    unittest.main()
