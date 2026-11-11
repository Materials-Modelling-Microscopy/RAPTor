"""Install RAPTor metadata in the static HTML shell served by Streamlit."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
import shutil


SITE_URL = "https://raptor.engr.wustl.edu/"
SITE_NAME = "RAPTor"
PAGE_TITLE = "RAPTor | Alloy Phase Stability and Thermodynamics"
DESCRIPTION = (
    "RAPTor provides CALPHAD-based phase-stability, phase-diagram, spinodal, "
    "and alloy-screening tools for multi-principal-element and refractory alloys."
)
SEO_MARKER = "RAPTOR_SEARCH_METADATA"


def metadata_markup() -> str:
    """Return metadata that must be present in the initial HTTP response."""
    structured_data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": SITE_NAME,
                "alternateName": "Rapid Alloy Phase-field generaTOR",
                "url": SITE_URL,
            },
            {
                "@type": "WebApplication",
                "name": SITE_NAME,
                "alternateName": "Rapid Alloy Phase-field generaTOR",
                "url": SITE_URL,
                "description": DESCRIPTION,
                "applicationCategory": "ScientificApplication",
                "operatingSystem": "Web",
            },
        ],
    }
    description = escape(DESCRIPTION, quote=True)
    title = escape(PAGE_TITLE)
    url = escape(SITE_URL, quote=True)
    return "\n".join(
        [
            f"<!-- {SEO_MARKER} -->",
            f'<meta name="description" content="{description}" />',
            f'<link rel="canonical" href="{url}" />',
            '<meta property="og:type" content="website" />',
            f'<meta property="og:site_name" content="{SITE_NAME}" />',
            f'<meta property="og:title" content="{title}" />',
            f'<meta property="og:description" content="{description}" />',
            f'<meta property="og:url" content="{url}" />',
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{title}" />',
            f'<meta name="twitter:description" content="{description}" />',
            '<script type="application/ld+json">',
            json.dumps(structured_data, separators=(",", ":")),
            "</script>",
            f"<!-- /{SEO_MARKER} -->",
        ]
    )


def patch_index_html(source: str) -> str:
    """Replace Streamlit defaults with RAPTor's crawlable identity."""
    if SEO_MARKER in source:
        return source

    default_title = "<title>Streamlit</title>"
    if default_title not in source:
        raise RuntimeError("Streamlit index.html no longer contains the expected title")

    patched = source.replace(
        default_title,
        f"<title>{escape(PAGE_TITLE)}</title>\n\n    {metadata_markup()}",
        1,
    )
    patched, replacements = re.subn(
        r"<noscript\b[^>]*>.*?</noscript>",
        "<noscript>RAPTor is an interactive alloy thermodynamics application. "
        "Please enable JavaScript to use its calculation tools.</noscript>",
        patched,
        count=1,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise RuntimeError("Streamlit index.html no longer contains a noscript block")
    return patched


def main() -> None:
    """Patch the installed Streamlit shell and replace its generic favicon."""
    import streamlit

    repository_root = Path(__file__).resolve().parents[1]
    streamlit_static = Path(streamlit.__file__).resolve().parent / "static"
    index_path = streamlit_static / "index.html"
    favicon_source = (
        repository_root / "alloy_web" / "assets" / "icons" / "raptor-wordmark.png"
    )
    favicon_destination = streamlit_static / "favicon.png"

    index_path.write_text(
        patch_index_html(index_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    shutil.copyfile(favicon_source, favicon_destination)


if __name__ == "__main__":
    main()
