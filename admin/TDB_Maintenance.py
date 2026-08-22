"""Private Streamlit interface for maintaining generated thermodynamic databases."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from external.Rapid_Phase_Field_Prediction.TDB_creation.tdb_maintenance import (
    MaintenanceError,
    apply_updates,
    load_catalog,
    preview_updates,
    validate_catalog,
)


def _authorize() -> None:
    password = os.environ.get("RAPTOR_TDB_MAINTENANCE_PASSWORD")
    if not password:
        return
    if st.session_state.get("tdb_maintenance_authorized"):
        return
    st.title("TDB maintenance")
    supplied = st.text_input("Maintenance password", type="password")
    if st.button("Unlock", type="primary") and hmac.compare_digest(supplied, password):
        st.session_state.tdb_maintenance_authorized = True
        st.rerun()
    st.stop()


st.set_page_config(page_title="TDB maintenance", page_icon=":material/build:", layout="wide")
_authorize()

st.title("TDB maintenance")
st.caption(
    "Private source-of-truth editor. Intermetallic energy edits are backed up and propagated "
    "to every generated TDB containing the corresponding binary phase."
)

with st.expander("How maintenance works"):
    st.markdown(
        """
        1. The binary TDBs are the authoritative building blocks; the JSON catalog indexes their
           intermetallic energies and interaction parameters.
        2. Filter to a binary pair, edit only **Energy (eV/formula)**, and review the impact preview.
        3. **Save and propagate** rewrites every matching phase occurrence and updates the catalog.
           A timestamped local backup and manifest are created before any file is changed.
        4. Run the integrity check after maintenance. Adding, deleting, or restructuring phases and
           editing interaction models are intentionally blocked in this release.

        If a deployed admin instance needs access control, set
        `RAPTOR_TDB_MAINTENANCE_PASSWORD` in addition to the navigation enable flag.
        """
    )

try:
    catalog = load_catalog()
except Exception as exc:
    st.error(f"Could not load the maintenance catalog: {exc}")
    st.stop()

binaries = pd.DataFrame(catalog["binaries"])
intermetallics = pd.DataFrame(catalog["intermetallics"])
interactions = pd.DataFrame(catalog["interactions"])

metric_cols = st.columns(3)
metric_cols[0].metric("Binary pairs", len(binaries))
metric_cols[1].metric("Intermetallic entries", len(intermetallics))
metric_cols[2].metric("Interaction parameters", len(interactions))

with st.expander("Integrity check"):
    if st.button("Validate catalog against binary TDBs"):
        problems = validate_catalog(catalog)
        if problems:
            st.error("Validation found inconsistencies.")
            st.dataframe(pd.DataFrame({"Problem": problems}), hide_index=True, width="stretch")
        else:
            st.success("Catalog and all binary TDB energies agree.")

binary_tab, intermetallic_tab, interaction_tab = st.tabs(
    ["Binary pairs", "Intermetallic energies", "Interaction parameters"]
)

with binary_tab:
    st.dataframe(binaries, hide_index=True, width="stretch")

with intermetallic_tab:
    pair_options = ["All"] + binaries["binary"].tolist()
    selected_pair = st.selectbox("Binary pair", pair_options)
    search = st.text_input("Find a phase", placeholder="For example: CR4HF2")
    visible = intermetallics.copy()
    if selected_pair != "All":
        visible = visible[visible["binary"] == selected_pair]
    if search:
        visible = visible[visible["phase"].str.contains(search, case=False, regex=False)]

    display_columns = [
        "id",
        "binary",
        "phase",
        "constituents",
        "atoms_per_formula",
        "energy_ev_per_formula",
        "energy_ev_per_atom",
        "energy_j_per_mol_formula",
    ]
    edited_visible = st.data_editor(
        visible[display_columns],
        hide_index=True,
        width="stretch",
        disabled=[column for column in display_columns if column != "energy_ev_per_formula"],
        column_config={
            "id": None,
            "energy_ev_per_formula": st.column_config.NumberColumn(
                "Energy (eV/formula)", format="%.10f", required=True
            ),
            "energy_ev_per_atom": st.column_config.NumberColumn("Energy (eV/atom)", format="%.8f"),
            "energy_j_per_mol_formula": st.column_config.NumberColumn("Energy (J/mol formula)", format="%.6f"),
        },
        key="intermetallic_editor",
    )

    edited_by_id = {row["id"]: row for row in intermetallics.to_dict("records")}
    for row in edited_visible.to_dict("records"):
        edited_by_id[row["id"]].update(row)
    edited_records = list(edited_by_id.values())
    try:
        preview = preview_updates(catalog, edited_records)
    except MaintenanceError as exc:
        st.error(str(exc))
        preview = {"changed_records": 0, "candidate_files": 0, "files": []}

    if preview["changed_records"]:
        st.warning(
            f"{preview['changed_records']} energy edit(s) will inspect "
            f"{preview['candidate_files']} TDB files. A timestamped backup is created first."
        )
        with st.expander("Candidate files"):
            st.code("\n".join(preview["files"]))
        confirm = st.checkbox("I have reviewed these energy edits")
        if st.button("Save and propagate", type="primary", disabled=not confirm):
            try:
                result = apply_updates(catalog, edited_records)
            except Exception as exc:
                st.error(f"No update was committed: {exc}")
            else:
                st.success(
                    f"Updated {result.changed_records} record(s) in {result.changed_files} TDB files "
                    f"({result.changed_occurrences} phase occurrence(s))."
                )
                st.caption(f"Backup: {result.backup_dir}")
                st.session_state.pop("intermetallic_editor", None)
                st.rerun()
    else:
        st.info("Edit an energy value to preview its impact. Phase creation and deletion are disabled.")

with interaction_tab:
    st.info("Read-only in this release. Adding and editing interaction models will follow later.")
    interaction_pair = st.selectbox("Binary pair", ["All"] + binaries["binary"].tolist(), key="interaction_pair")
    visible_interactions = interactions
    if interaction_pair != "All":
        visible_interactions = interactions[interactions["binary"] == interaction_pair]
    st.dataframe(visible_interactions, hide_index=True, width="stretch")
