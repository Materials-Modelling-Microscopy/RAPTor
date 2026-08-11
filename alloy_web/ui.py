import io
from typing import Sequence, Any

from pathlib import Path
import matplotlib.figure
import streamlit as st


AVAILABLE_ELEMENTS = [
    "Cr",
    "Hf",
    "Mo",
    "Nb",
    "Ta",
    "Ti",
    "V",
    "W",
    "Zr",
]


def element_selector(
    label: str,
    default: list[str],
    min_elements: int,
    max_elements: int,
):
    elements = st.multiselect(
        label,
        AVAILABLE_ELEMENTS,
        default=default,
    )

    if len(elements) < min_elements or len(elements) > max_elements:
        st.warning(
            f"Choose between {min_elements} and {max_elements} elements."
        )

    return elements


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
