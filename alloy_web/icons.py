from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
from textwrap import dedent

from PIL import Image
import streamlit as st


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
BRAND_FAVICON_PATH = ICON_DIR / "raptor-wordmark.png"
ICON_NAMES = {
    "brand",
    "symplex",
    "fractions",
    "diagram",
    "spinodal",
    "summary",
    "compare",
}


def icon_path(name: str) -> Path:
    if name not in ICON_NAMES:
        raise KeyError(f"Unknown RAPTor icon: {name}")
    return ICON_DIR / f"{name}.svg"


@lru_cache(maxsize=None)
def _icon_source(name: str) -> str:
    return icon_path(name).read_text(encoding="utf-8")


def icon_markup(name: str, size: int = 28, class_name: str = "") -> str:
    source = " ".join(_icon_source(name).split())
    attributes = (
        f'width="{int(size)}" height="{int(size)}" '
        f'class="{escape(class_name, quote=True)}" aria-hidden="true" focusable="false" '
    )
    return source.replace("<svg ", f"<svg {attributes}", 1)


def brand_favicon() -> Image.Image:
    """Load the compact RAPTor wordmark Streamlit uses as its favicon."""
    with Image.open(BRAND_FAVICON_PATH) as source:
        return source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)


def page_title(title: str, icon: str, subtitle: str | None = None) -> None:
    subtitle_markup = (
        f'<p class="raptor-page-subtitle">{escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    style = dedent(
        """
        <style>
            .raptor-page-heading {
                display: flex;
                align-items: center;
                gap: 0.82rem;
                margin: 0.15rem 0 0.9rem;
            }
            .raptor-page-icon {
                display: grid;
                place-items: center;
                flex: 0 0 auto;
                width: 3.2rem;
                height: 3.2rem;
                border-radius: 0.9rem;
                color: #5366c8;
                background: linear-gradient(145deg, rgba(75, 101, 205, 0.14), rgba(162, 72, 190, 0.10));
                border: 1px solid rgba(91, 103, 184, 0.16);
            }
            .raptor-page-heading h1 {
                margin: 0;
                padding: 0;
                line-height: 1.08;
                letter-spacing: -0.035em;
            }
            .raptor-page-subtitle {
                margin: 0.3rem 0 0;
                opacity: 0.64;
                line-height: 1.45;
            }
        </style>
        """,
    ).strip()
    heading = (
        '<div class="raptor-page-heading">'
        f'<div class="raptor-page-icon">{icon_markup(icon, 30)}</div>'
        f'<div><h1>{escape(title)}</h1>{subtitle_markup}</div>'
        "</div>"
    )
    st.markdown(style, unsafe_allow_html=True)
    st.markdown(heading, unsafe_allow_html=True)
