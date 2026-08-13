import io
from typing import Sequence, Any

from pathlib import Path
import matplotlib.figure
import streamlit as st

from alloy_web.config import AVAILABLE_ELEMENTS

# Mirrors the real periodic-table positions of the 9 available elements:
# groups 4-6 across periods 4-6.
_PERIODIC_LAYOUT = [
    ["Ti", "V", "Cr"],
    ["Zr", "Nb", "Mo"],
    ["Hf", "Ta", "W"],
]

def _element_grid_css(container_key: str) -> str:
    # st.container(key=...) stamps its outer div with a "st-key-<key>" class,
    # which actually wraps the child widgets in the DOM (unlike st.markdown
    # divs, which don't) — scope the styling to it so it doesn't leak onto
    # other buttons on the page (e.g. a page's "Run" button).
    scope = f".st-key-{container_key}"
    return f"""
    <style>
        {scope} [data-testid="stButton"] > button {{
            border-radius: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            padding: 0.5rem 0;
            border: 1px solid rgba(128, 128, 128, 0.25);
            background: rgba(128, 128, 128, 0.06);
            transition: all 120ms ease-in-out;
        }}

        {scope} [data-testid="stButton"] > button[kind="primary"] {{
            background: linear-gradient(145deg, rgba(75, 101, 205, 0.85), rgba(122, 72, 190, 0.80));
            border: 1px solid rgba(91, 103, 184, 0.35);
            color: white;
            box-shadow: 0 6px 16px rgba(60, 76, 160, 0.22);
        }}

        {scope} .raptor-element-order-badge {{
            margin-top: -0.35rem;
            margin-bottom: 0.35rem;
            text-align: center;
            font-size: 0.7rem;
            font-weight: 700;
            opacity: 0.65;
        }}
    </style>
    """


def element_selector(
    label: str,
    default: list[str],
    min_elements: int,
    max_elements: int,
    key: str | None = None,
):
    """
    Periodic-table-style button grid for picking elements.

    The selection is always kept in alphabetical order, regardless of the
    order the buttons were clicked. This is the canonical form the rest of
    the project expects: TDB files are named by joining the elements
    alphabetically (e.g. "Nb-Ti-V-Zr.tdb"), and adapters resolve them with
    `"-".join(alloy_system)`, so an unsorted list silently misses the file.
    Mole-fraction columns and composition rows line up with this list's
    index, so they follow the same alphabetical order.

    `key` scopes the selection state to one call site. Pages should always
    pass an explicit `key` — falling back to `label` risks collisions since
    several pages share the same label text (e.g. "Alloy system").
    """
    widget_key = key or label
    state_key = f"_element_grid__{widget_key}"
    container_key = f"raptor_element_grid__{widget_key}"

    if state_key not in st.session_state:
        st.session_state[state_key] = sorted(default)

    # Normalise state that predates the alphabetical ordering rule, so a
    # session left open across the change cannot keep feeding an unsorted
    # list to the TDB lookup.
    if st.session_state[state_key] != sorted(st.session_state[state_key]):
        st.session_state[state_key] = sorted(st.session_state[state_key])

    selected: list[str] = st.session_state[state_key]

    st.markdown(f"##### {label}")
    st.markdown(_element_grid_css(container_key), unsafe_allow_html=True)

    with st.container(key=container_key):
        for row in _PERIODIC_LAYOUT:
            cols = st.columns(3)
            for col, symbol in zip(cols, row):
                with col:
                    is_selected = symbol in selected
                    clicked = st.button(
                        symbol,
                        key=f"{state_key}__{symbol}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                    )
                    if is_selected:
                        order = selected.index(symbol) + 1
                        st.markdown(
                            f'<div class="raptor-element-order-badge">{order}</div>',
                            unsafe_allow_html=True,
                        )
                    if clicked:
                        if is_selected:
                            selected.remove(symbol)
                        else:
                            selected.append(symbol)
                        st.session_state[state_key] = sorted(selected)
                        st.rerun()

    if len(selected) < min_elements or len(selected) > max_elements:
        st.warning(
            f"Choose between {min_elements} and {max_elements} elements."
        )

    return list(selected)


def mole_fraction_inputs(elements: Sequence[str]) -> list[float]:
    if not elements:
        return []

    st.markdown("#### Mole fractions")

    # Keep the underlying value exactly equimolar. The widget controls how the
    # number is displayed, so rounding here can make valid ternaries sum to
    # 0.9999 and disable calculations across every analysis page.
    default_fraction = 1.0 / len(elements)
    values = []

    cols = st.columns(len(elements))

    for col, element in zip(cols, elements):
        with col:
            value = st.number_input(
                f"x_{element}",
                min_value=0.0,
                max_value=1.0,
                value=default_fraction,
                step=0.01,
                format="%.4f",
            )
            values.append(float(value))

    total = sum(values)

    if abs(total - 1.0) > 1e-6:
        st.warning(f"Mole fractions currently sum to {total:.4f}, not 1.0000.")

    return values


def figure_to_png_bytes(fig: matplotlib.figure.Figure) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=300,
        bbox_inches="tight",
    )
    buffer.seek(0)
    return buffer.getvalue()


def _pretty_key(key: str) -> str:
    return key.replace("_", " ").title()


def _pretty_value(value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, float):
        return f"{value:g}"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, (list, tuple)):
        if all(isinstance(x, (int, float)) for x in value):
            return ", ".join(f"{x:g}" for x in value)
        return " – ".join(str(x) for x in value)

    return str(value)


def show_input_summary(payload: dict, title: str = "Selected inputs"):
    """
    Display input parameters as a compact visual card instead of raw JSON.
    """

    with st.container(border=True):
        st.markdown(f"#### {title}")

        alloy_system = payload.get("alloy_system")
        if alloy_system:
            system_label = " – ".join(alloy_system)
            st.markdown(
                f"""
                <div style="
                    padding: 0.6rem 0.8rem;
                    border-radius: 0.6rem;
                    background-color: rgba(128, 128, 128, 0.10);
                    margin-bottom: 0.8rem;
                    font-size: 1.05rem;
                    font-weight: 600;
                ">
                    {system_label}
                </div>
                """,
                unsafe_allow_html=True,
            )

        hidden_keys = {"alloy_system", "tdb_dir"}

        visible_items = [
            (key, value)
            for key, value in payload.items()
            if key not in hidden_keys
        ]

        if visible_items:
            n_cols = 2
            rows = [
                visible_items[i : i + n_cols]
                for i in range(0, len(visible_items), n_cols)
            ]

            for row in rows:
                cols = st.columns(n_cols)

                for col, (key, value) in zip(cols, row):
                    with col:
                        st.markdown(
                            f"""
                            <div style="
                                padding: 0.55rem 0.7rem;
                                border-radius: 0.5rem;
                                border: 1px solid rgba(128, 128, 128, 0.25);
                                margin-bottom: 0.5rem;
                            ">
                                <div style="
                                    font-size: 0.75rem;
                                    opacity: 0.70;
                                    margin-bottom: 0.15rem;
                                ">
                                    {_pretty_key(key)}
                                </div>
                                <div style="
                                    font-size: 0.95rem;
                                    font-weight: 600;
                                ">
                                    {_pretty_value(value)}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

        # if "tdb_dir" in payload:
        #     with st.expander("TDB location"):
        #         st.code(str(payload["tdb_dir"]))


def show_result_data(
    data,
    title: str,
    file_name: str,
    key_prefix: str,
    preview_rows: int = 20,
):
    """
    Cleaner presentation for numerical output.

    Shows only a compact summary and download button by default.
    The table preview is hidden inside an expander.
    """

    n_rows, n_cols = data.shape

    with st.container(border=True):
        st.markdown(f"#### {title}")

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            st.metric("Rows", n_rows)

        with col2:
            st.metric("Columns", n_cols)

        with col3:
            st.download_button(
                "Download CSV",
                data=data.to_csv(index=False).encode("utf-8"),
                file_name=file_name,
                mime="text/csv",
                key=f"{key_prefix}_csv_download",
            )

        with st.expander("Preview data table"):
            max_rows = max(1, min(100, n_rows))
            default_rows = min(preview_rows, max_rows)

            n_preview = st.slider(
                "Rows to preview",
                min_value=1,
                max_value=max_rows,
                value=default_rows,
                key=f"{key_prefix}_preview_rows",
            )

            st.dataframe(
                data.head(n_preview),
                use_container_width=True,
                hide_index=True,
            )
