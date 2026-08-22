import copy
from pathlib import Path

import pytest

from external.Rapid_Phase_Field_Prediction.TDB_creation.tdb_maintenance import (
    MaintenanceError,
    apply_updates,
    build_catalog,
    load_catalog,
    preview_updates,
)


BINARY = """$ AB
PHASE BCC_A2  %  1  1.0  !
CONSTITUENT BCC_A2  :A,B :  !
PARAMETER L(BCC_A2,A,B;0)    298.15 -1200;    6000 N!

PHASE A1B1_MP  %  2 1.0  1.0 !
CONSTITUENT A1B1_MP  :A : B :  !
PARAMETER G(A1B1_MP,A:B;0)  298.15    -9648.5 + 1*GHSERA# + 1*GHSERB#; 6000 N !
"""

TERNARY = BINARY.replace("$ AB", "$ ABC") + """
PHASE A1C1_MP  %  2 1.0  1.0 !
CONSTITUENT A1C1_MP  :A : C :  !
PARAMETER G(A1C1_MP,A:C;0)  298.15 -100 + 1*GHSERA# + 1*GHSERC#; 6000 N !
"""


def _database(tmp_path: Path):
    tdb_dir = tmp_path / "tdb"
    tdb_dir.mkdir()
    (tdb_dir / "A-B.tdb").write_text(BINARY)
    (tdb_dir / "A-B-C.tdb").write_text(TERNARY)
    catalog_path = tmp_path / "catalog.json"
    catalog = load_catalog(catalog_path, tdb_dir)
    return tdb_dir, catalog_path, catalog


def test_catalog_lists_binary_intermetallics_and_interactions(tmp_path):
    tdb_dir, _catalog_path, catalog = _database(tmp_path)
    assert [item["binary"] for item in catalog["binaries"]] == ["A-B"]
    assert catalog["intermetallics"][0]["energy_ev_per_formula"] == pytest.approx(-0.1)
    assert catalog["interactions"][0]["value_j_per_mol"] == -1200
    assert build_catalog(tdb_dir)["intermetallics"] == catalog["intermetallics"]


def test_energy_edit_propagates_and_creates_backup(tmp_path):
    tdb_dir, catalog_path, catalog = _database(tmp_path)
    edited = copy.deepcopy(catalog["intermetallics"])
    edited[0]["energy_ev_per_formula"] = -0.2
    preview = preview_updates(catalog, edited, tdb_dir)
    assert preview["candidate_files"] == 2

    result = apply_updates(
        catalog,
        edited,
        tdb_dir=tdb_dir,
        catalog_path=catalog_path,
        backup_root=tmp_path / "backups",
    )
    assert result.changed_files == 2
    assert result.changed_occurrences == 2
    assert "-19297" in (tdb_dir / "A-B.tdb").read_text()
    assert "-19297" in (tdb_dir / "A-B-C.tdb").read_text()
    assert "-9648.5" in (result.backup_dir / "A-B.tdb").read_text()
    assert load_catalog(catalog_path, tdb_dir)["intermetallics"][0]["energy_ev_per_formula"] == -0.2


def test_addition_or_deletion_is_rejected(tmp_path):
    tdb_dir, catalog_path, catalog = _database(tmp_path)
    with pytest.raises(MaintenanceError, match="added or deleted"):
        apply_updates(
            catalog,
            [],
            tdb_dir=tdb_dir,
            catalog_path=catalog_path,
            backup_root=tmp_path / "backups",
        )
