import unittest

from alloy_web.analytics import google_analytics_html


class GoogleAnalyticsTests(unittest.TestCase):
    def test_installs_requested_measurement_id(self):
        markup = google_analytics_html("G-YDQW99XHHN")

        self.assertIn('const measurementId = "G-YDQW99XHHN";', markup)
        self.assertIn("googletagmanager.com/gtag/js", markup)
        self.assertIn('appWindow.gtag("config", measurementId', markup)

    def test_configures_tag_only_when_script_is_first_installed(self):
        markup = google_analytics_html("G-YDQW99XHHN")

        marker_check = 'if (!appDocument.getElementById(scriptId)) {'
        self.assertIn(marker_check, markup)
        self.assertGreater(
            markup.index('appWindow.gtag("config", measurementId)'),
            markup.index(marker_check),
        )
        self.assertEqual(markup.count('appWindow.gtag("config", measurementId)'), 1)

    def test_measurement_id_is_encoded_as_javascript_string(self):
        markup = google_analytics_html('G-TEST"; alert(1); //')

        self.assertIn(r'const measurementId = "G-TEST\"; alert(1); //";', markup)


if __name__ == "__main__":
    unittest.main()
