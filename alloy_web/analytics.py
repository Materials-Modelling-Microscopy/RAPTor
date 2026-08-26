"""Google Analytics integration for the Streamlit application."""

from __future__ import annotations

import inspect
import json
import os
from textwrap import dedent


DEFAULT_GA_MEASUREMENT_ID = "G-YDQW99XHHN"


def google_analytics_html(measurement_id: str) -> str:
    """Return the component script that installs gtag on the parent document.

    Streamlit components run in an iframe. The script deliberately installs the
    Google tag on the parent page so Analytics records the actual application
    URL, not the component iframe URL. The script-element marker prevents
    Streamlit widget reruns from configuring the tag (and producing a duplicate
    page view) again. GA4 Enhanced Measurement handles subsequent route changes.
    """
    encoded_measurement_id = json.dumps(measurement_id)
    return dedent(
        f"""
        <script>
        (() => {{
          const measurementId = {encoded_measurement_id};
          const appWindow = window.parent;
          const appDocument = appWindow.document;
          const scriptId = "raptor-google-analytics";

          appWindow.dataLayer = appWindow.dataLayer || [];
          appWindow.gtag = appWindow.gtag || function() {{
            appWindow.dataLayer.push(arguments);
          }};

          if (!appDocument.getElementById(scriptId)) {{
            const tag = appDocument.createElement("script");
            tag.id = scriptId;
            tag.async = true;
            tag.src = `https://www.googletagmanager.com/gtag/js?id=${{measurementId}}`;
            appDocument.head.appendChild(tag);

            appWindow.gtag("js", new Date());
            appWindow.gtag("config", measurementId);
          }}
        }})();
        </script>
        """
    ).strip()


def enable_google_analytics() -> None:
    """Install Google Analytics once for the current browser page."""
    measurement_id = os.environ.get(
        "RAPTOR_GA_MEASUREMENT_ID", DEFAULT_GA_MEASUREMENT_ID
    ).strip()
    if not measurement_id:
        return

    # Import lazily so non-web users of alloy_web do not need Streamlit.
    import streamlit as st

    markup = google_analytics_html(measurement_id)
    if "unsafe_allow_javascript" in inspect.signature(st.html).parameters:
        # Streamlit 1.56+ executes this directly in the application document.
        st.html(markup, width="content", unsafe_allow_javascript=True)
        return

    # Compatibility with the older Streamlit releases allowed by this project.
    # The component iframe has same-origin access, so the same script can install
    # gtag in the parent application document.
    from streamlit.components.v1 import html

    html(markup, height=0, width=0, scrolling=False)
