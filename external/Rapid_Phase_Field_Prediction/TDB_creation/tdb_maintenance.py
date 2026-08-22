"""Path-safe parsing and transactional maintenance for generated TDB files.

The binary TDB files are treated as the authoritative building blocks.  This
module extracts a small, reviewable JSON catalog from them and propagates an
intermetallic energy edit to every generated TDB containing the same binary
phase.  It deliberately does not support adding or deleting records yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping, Sequence


MODULE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = MODULE_DIR.parent
DEFAULT_TDB_DIR = PACKAGE_DIR / "input" / "tdb"
DEFAULT_CATALOG_PATH = MODULE_DIR / "tdb_maintenance_catalog.json"
DEFAULT_BACKUP_DIR = MODULE_DIR / "maintenance_backups"

EV_TO_J_PER_MOL = 96485.0
CATALOG_VERSION = 1
SOLUTION_PHASES = {"FCC_A1": "FCC", "BCC_A2": "BCC", "HCP_A3": "HCP"}

_PHASE_BLOCK_RE = re.compile(r"(?ms)^PHASE\s+(?P<phase>\S+).*?(?=^PHASE\s+|\Z)")
_CONSTITUENT_RE = re.compile(r"(?mi)^CONSTITUENT\s+\S+\s+:(?P<body>.*?)!\s*$")
_PHASE_RE = re.compile(r"(?mi)^PHASE\s+(?P<phase>\S+)\s+%\s+\d+\s+(?P<sites>.*?)!\s*$")
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"


class MaintenanceError(RuntimeError):
    """Raised when an update cannot be applied without ambiguity."""


@dataclass(frozen=True)
class UpdateResult:
    changed_records: int
    changed_files: int
    changed_occurrences: int
    backup_dir: Path | None
    files: tuple[str, ...]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _binary_files(tdb_dir: Path) -> list[Path]:
    return sorted(path for path in tdb_dir.glob("*.tdb") if len(path.stem.split("-")) == 2)


def _constituent_signature(block: str) -> str:
    match = _CONSTITUENT_RE.search(block)
    if not match:
        raise MaintenanceError("Intermetallic phase has no CONSTITUENT line")
    return re.sub(r"\s+", "", match.group("body").upper())


def _site_count(block: str) -> float:
    match = _PHASE_RE.search(block)
    if not match:
        raise MaintenanceError("Intermetallic phase has no parseable PHASE line")
    values = re.findall(_NUMBER, match.group("sites"))
    return sum(float(value) for value in values)


def _energy_pattern(phase: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?mi)^(?P<prefix>\s*PARAMETER\s+G\({re.escape(phase)}\s*,.*?\)\s+298\.15\s+)(?P<energy>{_NUMBER})"
    )


def _intermetallic_records(binary: str, text: str) -> list[dict]:
    records: list[dict] = []
    ordinals: dict[tuple[str, str], int] = {}
    for phase_match in _PHASE_BLOCK_RE.finditer(text):
        phase = phase_match.group("phase").upper()
        if phase in SOLUTION_PHASES:
            continue
        block = phase_match.group(0)
        energy_match = _energy_pattern(phase).search(block)
        if not energy_match:
            continue
        signature = _constituent_signature(block)
        key = (phase, signature)
        ordinal = ordinals.get(key, 0)
        ordinals[key] = ordinal + 1
        energy_j = float(energy_match.group("energy"))
        sites = _site_count(block)
        record_id = f"{binary}|{phase}|{signature}|{ordinal}"
        records.append(
            {
                "id": record_id,
                "binary": binary,
                "phase": phase,
                "constituents": signature,
                "occurrence": ordinal,
                "atoms_per_formula": sites,
                "energy_j_per_mol_formula": energy_j,
                "energy_ev_per_formula": energy_j / EV_TO_J_PER_MOL,
                "energy_ev_per_atom": energy_j / EV_TO_J_PER_MOL / sites if sites else None,
            }
        )
    return records


def _interaction_records(binary: str, text: str) -> list[dict]:
    records: list[dict] = []
    pattern = re.compile(
        rf"(?mi)^\s*PARAMETER\s+L\((?P<phase>FCC_A1|BCC_A2|HCP_A3)\s*,(?P<constituents>[^;]+);(?P<order>\d+)\)\s+298\.15\s+(?P<value>{_NUMBER})"
    )
    for match in pattern.finditer(text):
        value_j = float(match.group("value"))
        records.append(
            {
                "id": f"{binary}|{match.group('phase').upper()}|{match.group('order')}",
                "binary": binary,
                "lattice": SOLUTION_PHASES[match.group("phase").upper()],
                "order": int(match.group("order")),
                "constituents": re.sub(r"\s+", "", match.group("constituents").upper()),
                "value_j_per_mol": value_j,
                "value_ev_per_formula": value_j / EV_TO_J_PER_MOL,
            }
        )
    return records


def build_catalog(tdb_dir: Path = DEFAULT_TDB_DIR) -> dict:
    """Parse every binary TDB into the canonical maintenance catalog."""
    binaries: list[dict] = []
    intermetallics: list[dict] = []
    interactions: list[dict] = []
    for path in _binary_files(tdb_dir):
        binary = path.stem
        text = path.read_text(encoding="utf-8")
        binary_intermetallics = _intermetallic_records(binary, text)
        binary_interactions = _interaction_records(binary, text)
        binaries.append(
            {
                "binary": binary,
                "file": path.name,
                "intermetallic_count": len(binary_intermetallics),
                "interaction_count": len(binary_interactions),
            }
        )
        intermetallics.extend(binary_intermetallics)
        interactions.extend(binary_interactions)
    return {
        "schema_version": CATALOG_VERSION,
        "energy_unit": "eV/formula",
        "interaction_unit": "J/mol",
        "binaries": binaries,
        "intermetallics": intermetallics,
        "interactions": interactions,
    }


def save_catalog(catalog: Mapping, path: Path = DEFAULT_CATALOG_PATH) -> None:
    payload = dict(catalog)
    payload["schema_version"] = CATALOG_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=False) + "\n")


def load_catalog(
    path: Path = DEFAULT_CATALOG_PATH,
    tdb_dir: Path = DEFAULT_TDB_DIR,
    *,
    create: bool = True,
) -> dict:
    if not path.exists():
        catalog = build_catalog(tdb_dir)
        if create:
            save_catalog(catalog, path)
        return catalog
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != CATALOG_VERSION:
        raise MaintenanceError(f"Unsupported catalog schema: {catalog.get('schema_version')!r}")
    return catalog


def _record_lookup(catalog: Mapping) -> dict[str, dict]:
    records = catalog.get("intermetallics", [])
    lookup = {record["id"]: dict(record) for record in records}
    if len(lookup) != len(records):
        raise MaintenanceError("Catalog contains duplicate intermetallic IDs")
    return lookup


def _validate_updates(current: Mapping, edited: Sequence[Mapping]) -> list[tuple[dict, dict]]:
    current_lookup = _record_lookup(current)
    edited_lookup = {str(record.get("id")): dict(record) for record in edited}
    if set(edited_lookup) != set(current_lookup):
        raise MaintenanceError("Records cannot be added or deleted in this release")
    changes: list[tuple[dict, dict]] = []
    for record_id, old in current_lookup.items():
        new = edited_lookup[record_id]
        for immutable in ("binary", "phase", "constituents", "occurrence", "atoms_per_formula"):
            if new.get(immutable) != old.get(immutable):
                raise MaintenanceError(f"{immutable} is not editable for {record_id}")
        try:
            energy = float(new["energy_ev_per_formula"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MaintenanceError(f"Invalid energy for {record_id}") from exc
        if not math.isfinite(energy):
            raise MaintenanceError(f"Energy must be finite for {record_id}")
        new["energy_ev_per_formula"] = energy
        new["energy_j_per_mol_formula"] = energy * EV_TO_J_PER_MOL
        atoms = float(old["atoms_per_formula"])
        new["energy_ev_per_atom"] = energy / atoms if atoms else None
        if not math.isclose(energy, float(old["energy_ev_per_formula"]), rel_tol=0, abs_tol=1e-12):
            changes.append((old, new))
    return changes


def preview_updates(current: Mapping, edited: Sequence[Mapping], tdb_dir: Path = DEFAULT_TDB_DIR) -> dict:
    changes = _validate_updates(current, edited)
    affected: set[str] = set()
    for old, _new in changes:
        pair = set(old["binary"].split("-"))
        for path in tdb_dir.glob("*.tdb"):
            if pair.issubset(path.stem.split("-")):
                affected.add(path.name)
    return {"changed_records": len(changes), "candidate_files": len(affected), "files": sorted(affected)}


def _replace_record(text: str, record: Mapping, new_energy_j: float) -> tuple[str, int]:
    phase = str(record["phase"]).upper()
    signature = str(record["constituents"]).upper()
    wanted_ordinal = int(record["occurrence"])
    matching_ordinal = 0
    replacement_count = 0
    chunks: list[str] = []
    cursor = 0
    for block_match in _PHASE_BLOCK_RE.finditer(text):
        block = block_match.group(0)
        if block_match.group("phase").upper() != phase:
            continue
        try:
            block_signature = _constituent_signature(block)
        except MaintenanceError:
            continue
        if block_signature != signature:
            continue
        if matching_ordinal == wanted_ordinal:
            pattern = _energy_pattern(phase)
            updated_block, count = pattern.subn(
                lambda match: match.group("prefix") + format(new_energy_j, ".15g"),
                block,
                count=1,
            )
            if count != 1:
                raise MaintenanceError(f"Could not update {record['id']}")
            chunks.append(text[cursor:block_match.start()])
            chunks.append(updated_block)
            cursor = block_match.end()
            replacement_count += 1
            break
        matching_ordinal += 1
    if not replacement_count:
        return text, 0
    chunks.append(text[cursor:])
    return "".join(chunks), replacement_count


def apply_updates(
    current: Mapping,
    edited: Sequence[Mapping],
    *,
    tdb_dir: Path = DEFAULT_TDB_DIR,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    backup_root: Path = DEFAULT_BACKUP_DIR,
) -> UpdateResult:
    """Validate, back up, propagate, and persist energy edits as one operation."""
    changes = _validate_updates(current, edited)
    if not changes:
        return UpdateResult(0, 0, 0, None, ())

    staged: dict[Path, str] = {}
    occurrences = 0
    for path in sorted(tdb_dir.glob("*.tdb")):
        text = path.read_text(encoding="utf-8")
        updated = text
        file_occurrences = 0
        elements = set(path.stem.split("-"))
        for old, new in changes:
            if not set(old["binary"].split("-")).issubset(elements):
                continue
            updated, count = _replace_record(updated, old, new["energy_j_per_mol_formula"])
            file_occurrences += count
        if updated != text:
            staged[path] = updated
            occurrences += file_occurrences

    binary_names = {old["binary"] + ".tdb" for old, _new in changes}
    missing_binaries = sorted(name for name in binary_names if tdb_dir / name not in staged)
    if missing_binaries:
        raise MaintenanceError("The authoritative binary phase was not found: " + ", ".join(missing_binaries))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / timestamp
    suffix = 1
    while backup_dir.exists():
        backup_dir = backup_root / f"{timestamp}-{suffix}"
        suffix += 1
    backup_dir.mkdir(parents=True)
    for path in staged:
        shutil.copy2(path, backup_dir / path.name)
    if catalog_path.exists():
        shutil.copy2(catalog_path, backup_dir / catalog_path.name)

    updated_catalog = dict(current)
    new_lookup = {new["id"]: new for _old, new in changes}
    updated_catalog["intermetallics"] = [new_lookup.get(record["id"], record) for record in current["intermetallics"]]
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "records": [old["id"] for old, _new in changes],
        "files": [path.name for path in staged],
    }
    _atomic_write(backup_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")

    try:
        for path, text in staged.items():
            _atomic_write(path, text)
        save_catalog(updated_catalog, catalog_path)
    except Exception:
        for path in staged:
            shutil.copy2(backup_dir / path.name, path)
        if (backup_dir / catalog_path.name).exists():
            shutil.copy2(backup_dir / catalog_path.name, catalog_path)
        raise

    return UpdateResult(
        len(changes), len(staged), occurrences, backup_dir, tuple(path.name for path in staged)
    )


def validate_catalog(catalog: Mapping, tdb_dir: Path = DEFAULT_TDB_DIR) -> list[str]:
    """Return consistency problems without changing the catalog or TDB files."""
    problems: list[str] = []
    try:
        lookup = _record_lookup(catalog)
    except MaintenanceError as exc:
        return [str(exc)]
    parsed = build_catalog(tdb_dir)
    parsed_lookup = _record_lookup(parsed)
    if set(lookup) != set(parsed_lookup):
        missing = set(lookup) - set(parsed_lookup)
        extra = set(parsed_lookup) - set(lookup)
        if missing:
            problems.append(f"{len(missing)} catalog records are absent from binary TDBs")
        if extra:
            problems.append(f"{len(extra)} binary TDB records are absent from the catalog")
    for record_id in set(lookup) & set(parsed_lookup):
        expected = float(lookup[record_id]["energy_ev_per_formula"])
        actual = float(parsed_lookup[record_id]["energy_ev_per_formula"])
        if not math.isclose(expected, actual, rel_tol=0, abs_tol=1e-9):
            problems.append(f"Energy mismatch: {record_id}")
    return problems
