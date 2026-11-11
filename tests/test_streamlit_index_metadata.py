import unittest

from scripts.patch_streamlit_index import (
    DESCRIPTION,
    PAGE_TITLE,
    SITE_URL,
    patch_index_html,
)


STREAMLIT_SHELL = """<!doctype html>
<html>
  <head><title>Streamlit</title></head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>
"""

CURRENT_STREAMLIT_SHELL = """<!doctype html>
<html>
  <head><title>Streamlit</title></head>
  <body>
    <noscript>
      <p>You need to enable JavaScript to run this app.</p>
      <p>A Streamlit app can also offer its contents to automated agents.</p>
    </noscript>
    <div id="root"></div>
  </body>
</html>
"""


class StreamlitIndexMetadataTests(unittest.TestCase):
    def test_patch_adds_search_metadata_to_initial_html(self):
        result = patch_index_html(STREAMLIT_SHELL)

        self.assertIn(f"<title>{PAGE_TITLE}</title>", result)
        self.assertIn(f'content="{DESCRIPTION}"', result)
        self.assertIn(f'<link rel="canonical" href="{SITE_URL}"', result)
        self.assertIn('"@type":"WebSite"', result)
        self.assertIn('"@type":"WebApplication"', result)
        self.assertNotIn("<title>Streamlit</title>", result)
        self.assertNotIn("You need to enable JavaScript to run this app.", result)

    def test_patch_is_idempotent(self):
        once = patch_index_html(STREAMLIT_SHELL)

        self.assertEqual(patch_index_html(once), once)

    def test_patch_replaces_multiline_noscript_block(self):
        result = patch_index_html(CURRENT_STREAMLIT_SHELL)

        self.assertNotIn("You need to enable JavaScript to run this app.", result)
        self.assertNotIn("automated agents", result)
        self.assertIn("interactive alloy thermodynamics application", result)


if __name__ == "__main__":
    unittest.main()
