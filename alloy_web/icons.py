from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
from textwrap import dedent

from PIL import Image, ImageDraw
import streamlit as st


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
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
    """Render the RAPTor mark to a small raster image Streamlit can use as a favicon."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(70, 86, 181, 255))

    triangle = [(32, 9), (11, 52), (53, 52), (32, 9)]
    draw.line(triangle, fill="white", width=5, joint="curve")
    for x, y in triangle[:3]:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="white")

    curve = []
    start = (17.0, 40.0)
    control = (30.0, 25.0)
    end = (47.0, 36.0)
    for index in range(21):
        fraction = index / 20.0
        inverse = 1.0 - fraction
        curve.append(
            (
                inverse * inverse * start[0]
                + 2 * inverse * fraction * control[0]
                + fraction * fraction * end[0],
                inverse * inverse * start[1]
                + 2 * inverse * fraction * control[1]
                + fraction * fraction * end[1],
            )
        )
    draw.line(curve, fill="white", width=3)
    return image


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
