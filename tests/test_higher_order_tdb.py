from pathlib import Path

import pytest

from external.Rapid_Phase_Field_Prediction.TDB_creation.higher_order_tdb import (
    BEGIN_MARKER,
    BinaryEndmember,
    TernaryInteraction,
    _replace_or_append_section,
    remove_higher_order_intermetallic_sections,
    render_higher_order_section,
    render_ternary_c15_phase,
)


def _binaries():
    return {
        ("Nb", "V"): BinaryEndmember("Nb", "V", -0.04),
        ("Zr", "V"): BinaryEndmember("Zr", "V", 0.04),
        ("V", "Nb"): BinaryEndmember("V", "Nb", 0.47),
        ("V", "Zr"): BinaryEndmember("V", "Zr", 0.81),
    }


def test_render_a_sublattice_interaction_uses_explicit_endmembers():
    item = TernaryInteraction("L_A(Nb,Zr|B=V)", "A", "Nb", "Zr", "V", "DFT", 0.012)
    block = render_ternary_c15_phase(item, _binaries())
    assert "PHASE C15A_NB_ZR_V  %  2  2  4 !" in block
    assert "CONSTITUENT C15A_NB_ZR_V  :NB,ZR :V :" in block
    assert "2*GHSERNB# + 4*GHSERV#" in block
    assert "2*GHSERZR# + 4*GHSERV#" in block
    assert "PARAMETER L(C15A_NB_ZR_V,NB,ZR:V;0)" in block
    assert "+NB2V4_MP" not in block


def test_render_b_sublattice_interaction_has_correct_site_order():
    item = TernaryInteraction("L_B(A=V|Nb,Zr)", "B", "Nb", "Zr", "V", "ML", -0.48)
    block = render_ternary_c15_phase(item, _binaries())
    assert "PHASE C15B_V_NB_ZR" in block
    assert "CONSTITUENT C15B_V_NB_ZR  :V :NB,ZR :" in block
    assert "PARAMETER L(C15B_V_NB_ZR,V:NB,ZR;0)" in block


def test_marked_section_is_idempotently_replaced_and_legacy_text_survives():
    item = TernaryInteraction("L_A(Nb,Zr|B=V)", "A", "Nb", "Zr", "V", "DFT", 0.012)
    section, count = render_higher_order_section(("Nb", "V", "Zr"), _binaries(), (item,))
    original = "$ HEADER\n\nPHASE LEGACY_MP % 1 1 !\n"
    once = _replace_or_append_section(original, section)
    twice = _replace_or_append_section(once, section)
    assert count == 1
    assert once == twice
    assert once.count(BEGIN_MARKER) == 1
    assert "PHASE LEGACY_MP" in once


def test_removal_deletes_only_marked_section(tmp_path):
    tdb_dir = tmp_path / "tdb"
    tdb_dir.mkdir()
    item = TernaryInteraction("L_A(Nb,Zr|B=V)", "A", "Nb", "Zr", "V", "DFT", 0.012)
    section, _count = render_higher_order_section(("Nb", "V", "Zr"), _binaries(), (item,))
    legacy = "$ HEADER\n\nPHASE LEGACY_MP % 1 1 !\n"
    (tdb_dir / "Nb-V-Zr.tdb").write_text(_replace_or_append_section(legacy, section))

    preview = remove_higher_order_intermetallic_sections(tdb_dir=tdb_dir)
    assert preview.removed_sections == 1
    assert preview.changed_files == 0

    result = remove_higher_order_intermetallic_sections(
        tdb_dir=tdb_dir,
        backup_root=tmp_path / "backups",
        dry_run=False,
    )
    assert result.changed_files == 1
    assert (tdb_dir / "Nb-V-Zr.tdb").read_text() == legacy
    assert BEGIN_MARKER in (result.backup_dir / "tdb" / "Nb-V-Zr.tdb").read_text()
