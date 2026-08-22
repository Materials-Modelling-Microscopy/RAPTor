"""Safely add ternary C15 CEF models to generated TDB files.

This module intentionally remains separate from ``tdb_maintenance``.  It reads
the private higher-order workflow products at update time, renders a marked and
replaceable section, snapshots the complete TDB directory, and only then writes
the staged files.  No higher-order source dataset is copied into RAPTor.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Sequence


MODULE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = MODULE_DIR.parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DEFAULT_TDB_DIR = PACKAGE_DIR / "input" / "tdb"
DEFAULT_HIGHER_ORDER_ROOT = PROJECT_ROOT / "higher-order-intermetallics"
DEFAULT_BINARY_PATH = DEFAULT_HIGHER_ORDER_ROOT / "data/processed/binary_formation_energies.csv"
DEFAULT_INTERACTION_PATH = (
    DEFAULT_HIGHER_ORDER_ROOT / "results/cef/cef_ternary_interaction_parameters.csv"
)
DEFAULT_BACKUP_ROOT = MODULE_DIR / "maintenance_backups" / "higher_order"

EV_TO_J_PER_MOL = 96485.0
FORMULA_ATOMS = 6.0
SECTION_VERSION = 1
BEGIN_MARKER = f"$ RAPTOR_HIGHER_ORDER_C15_BEGIN VERSION={SECTION_VERSION}"
END_MARKER = "$ RAPTOR_HIGHER_ORDER_C15_END"
SECTION_RE = re.compile(
    rf"(?ms)^\$ RAPTOR_HIGHER_ORDER_C15_BEGIN.*?^\$ RAPTOR_HIGHER_ORDER_C15_END\s*"
)


class HigherOrderTDBError(RuntimeError):
    """Raised when higher-order data or a proposed TDB update is unsafe."""


@dataclass(frozen=True)
class BinaryEndmember:
    a_element: str
    b_element: str
    formation_energy_ev_atom: float


@dataclass(frozen=True)
class TernaryInteraction:
    parameter_id: str
    mixed_sublattice: str
    mixed_element_1: str
    mixed_element_2: str
    opposite_element: str
    source_energy_source: str
    cef_parameter_ev_atom: float

    @property
    def elements(self) -> frozenset[str]:
        return frozenset((self.mixed_element_1, self.mixed_element_2, self.opposite_element))


@dataclass(frozen=True)
class HigherOrderUpdatePlan:
    source_binary_count: int
    source_interaction_count: int
    source_dft_count: int
    source_ml_count: int
    affected_files: int
    generated_phase_occurrences: int
    existing_generated_sections: int
    preserved_legacy_ternary_phases: int
    files: tuple[str, ...]


@dataclass(frozen=True)
class HigherOrderUpdateResult:
    plan: HigherOrderUpdatePlan
    changed_files: int
    backup_dir: Path | None


@dataclass(frozen=True)
class HigherOrderRemovalResult:
    changed_files: int
    removed_sections: int
    backup_dir: Path | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
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


def _finite_float(row: dict[str, str], field: str, identifier: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise HigherOrderTDBError(f"Invalid {field} for {identifier}") from exc
    if not math.isfinite(value):
        raise HigherOrderTDBError(f"Non-finite {field} for {identifier}")
    return value


def load_higher_order_c15_data(
    binary_path: Path = DEFAULT_BINARY_PATH,
    interaction_path: Path = DEFAULT_INTERACTION_PATH,
) -> tuple[dict[tuple[str, str], BinaryEndmember], tuple[TernaryInteraction, ...]]:
    """Read and strictly validate the 72 binary and 504 ternary C15 records."""
    if not binary_path.is_file():
        raise HigherOrderTDBError(f"Binary C15 dataset not found: {binary_path}")
    if not interaction_path.is_file():
        raise HigherOrderTDBError(f"Ternary C15 dataset not found: {interaction_path}")

    binaries: dict[tuple[str, str], BinaryEndmember] = {}
    with binary_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            a_element = row["a_element"].strip().title()
            b_element = row["b_element"].strip().title()
            identifier = row.get("configuration_id", f"{a_element}:{b_element}")
            if not a_element or not b_element or a_element == b_element:
                raise HigherOrderTDBError(f"Invalid directional binary: {identifier}")
            key = (a_element, b_element)
            if key in binaries:
                raise HigherOrderTDBError(f"Duplicate directional binary: {identifier}")
            binaries[key] = BinaryEndmember(
                a_element,
                b_element,
                _finite_float(row, "formation_energy_ev_atom", identifier),
            )

    interactions: list[TernaryInteraction] = []
    seen_parameters: set[str] = set()
    with interaction_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            parameter_id = row["parameter_id"].strip()
            if parameter_id in seen_parameters:
                raise HigherOrderTDBError(f"Duplicate ternary parameter: {parameter_id}")
            seen_parameters.add(parameter_id)
            mixed_1, mixed_2 = sorted(
                (row["mixed_element_1"].strip().title(), row["mixed_element_2"].strip().title())
            )
            opposite = row["opposite_element"].strip().title()
            mixed_sublattice = row["mixed_sublattice"].strip().upper()
            source = row["source_energy_source"].strip().upper()
            if mixed_sublattice not in {"A", "B"}:
                raise HigherOrderTDBError(f"Invalid sublattice for {parameter_id}")
            if source not in {"DFT", "ML"}:
                raise HigherOrderTDBError(f"Invalid energy source for {parameter_id}")
            if len({mixed_1, mixed_2, opposite}) != 3:
                raise HigherOrderTDBError(f"Ternary elements must be distinct for {parameter_id}")
            if mixed_sublattice == "A":
                endmember_keys = ((mixed_1, opposite), (mixed_2, opposite))
            else:
                endmember_keys = ((opposite, mixed_1), (opposite, mixed_2))
            if any(key not in binaries for key in endmember_keys):
                raise HigherOrderTDBError(f"Missing endmember for {parameter_id}")
            stated_endmembers = (
                _finite_float(row, "binary_endmember_1_energy_ev_atom", parameter_id),
                _finite_float(row, "binary_endmember_2_energy_ev_atom", parameter_id),
            )
            actual_endmembers = tuple(
                binaries[key].formation_energy_ev_atom for key in endmember_keys
            )
            if not all(
                math.isclose(stated, actual, rel_tol=0, abs_tol=1e-8)
                for stated, actual in zip(stated_endmembers, actual_endmembers)
            ):
                raise HigherOrderTDBError(f"Binary endmember mismatch for {parameter_id}")
            source_energy = _finite_float(row, "source_ternary_energy_ev_atom", parameter_id)
            baseline = _finite_float(row, "binary_baseline_ev_atom", parameter_id)
            residual = _finite_float(row, "ternary_residual_ev_atom", parameter_id)
            cef_parameter = _finite_float(row, "cef_parameter_ev_atom", parameter_id)
            if not math.isclose(baseline, sum(actual_endmembers) / 2, rel_tol=0, abs_tol=1e-8):
                raise HigherOrderTDBError(f"Binary baseline mismatch for {parameter_id}")
            if not math.isclose(residual, source_energy - baseline, rel_tol=0, abs_tol=1e-8):
                raise HigherOrderTDBError(f"Ternary residual mismatch for {parameter_id}")
            if not math.isclose(cef_parameter, 4 * residual, rel_tol=0, abs_tol=1e-8):
                raise HigherOrderTDBError(f"CEF normalization mismatch for {parameter_id}")
            interactions.append(
                TernaryInteraction(
                    parameter_id,
                    mixed_sublattice,
                    mixed_1,
                    mixed_2,
                    opposite,
                    source,
                    cef_parameter,
                )
            )

    elements = {element for pair in binaries for element in pair}
    expected_binary_keys = {(a, b) for a in elements for b in elements if a != b}
    if len(elements) != 9 or set(binaries) != expected_binary_keys:
        raise HigherOrderTDBError(
            "Expected all 72 directional binaries for exactly nine distinct elements"
        )
    if len(interactions) != 504:
        raise HigherOrderTDBError(f"Expected 504 ternary interactions; found {len(interactions)}")

    by_system: Counter[frozenset[str]] = Counter(item.elements for item in interactions)
    if len(by_system) != 84 or set(by_system.values()) != {6}:
        raise HigherOrderTDBError("Expected 84 ternary systems with six configurations each")
    return binaries, tuple(sorted(interactions, key=lambda item: item.parameter_id))


def _phase_name(item: TernaryInteraction) -> str:
    if item.mixed_sublattice == "A":
        tokens = (item.mixed_element_1, item.mixed_element_2, item.opposite_element)
    else:
        tokens = (item.opposite_element, item.mixed_element_1, item.mixed_element_2)
    return "C15" + item.mixed_sublattice + "_" + "_".join(token.upper() for token in tokens)


def _energy_expression(endmember: BinaryEndmember) -> str:
    formation_j = endmember.formation_energy_ev_atom * FORMULA_ATOMS * EV_TO_J_PER_MOL
    return (
        f"{formation_j:.15g} + 2*GHSER{endmember.a_element.upper()}# "
        f"+ 4*GHSER{endmember.b_element.upper()}#"
    )


def render_ternary_c15_phase(
    item: TernaryInteraction,
    binaries: dict[tuple[str, str], BinaryEndmember],
) -> str:
    """Render one independently parameterized two-sublattice C15 phase."""
    phase = _phase_name(item)
    first = item.mixed_element_1
    second = item.mixed_element_2
    opposite = item.opposite_element
    interaction_j = item.cef_parameter_ev_atom * FORMULA_ATOMS * EV_TO_J_PER_MOL
    if item.mixed_sublattice == "A":
        constituent = f":{first.upper()},{second.upper()} :{opposite.upper()} :"
        first_configuration = f"{first.upper()}:{opposite.upper()}"
        second_configuration = f"{second.upper()}:{opposite.upper()}"
        interaction_configuration = (
            f"{first.upper()},{second.upper()}:{opposite.upper()}"
        )
        first_endmember = binaries[(first, opposite)]
        second_endmember = binaries[(second, opposite)]
    else:
        constituent = f":{opposite.upper()} :{first.upper()},{second.upper()} :"
        first_configuration = f"{opposite.upper()}:{first.upper()}"
        second_configuration = f"{opposite.upper()}:{second.upper()}"
        interaction_configuration = (
            f"{opposite.upper()}:{first.upper()},{second.upper()}"
        )
        first_endmember = binaries[(opposite, first)]
        second_endmember = binaries[(opposite, second)]

    return "\n".join(
        (
            f"$ {item.parameter_id} SOURCE={item.source_energy_source}",
            f"PHASE {phase}  %  2  2  4 !",
            f"CONSTITUENT {phase}  {constituent}  !",
            f"PARAMETER G({phase},{first_configuration};0)  298.15  {_energy_expression(first_endmember)};  6000 N !",
            f"PARAMETER G({phase},{second_configuration};0)  298.15  {_energy_expression(second_endmember)};  6000 N !",
            f"PARAMETER L({phase},{interaction_configuration};0)  298.15  {interaction_j:.15g};  6000 N !",
        )
    )


def render_higher_order_section(
    elements: Iterable[str],
    binaries: dict[tuple[str, str], BinaryEndmember],
    interactions: Sequence[TernaryInteraction],
) -> tuple[str, int]:
    available = {element.title() for element in elements}
    selected = [item for item in interactions if item.elements.issubset(available)]
    blocks = [render_ternary_c15_phase(item, binaries) for item in selected]
    section = "\n\n".join((BEGIN_MARKER, *blocks, END_MARKER)) + "\n"
    return section, len(selected)


def _replace_or_append_section(text: str, section: str) -> str:
    if SECTION_RE.search(text):
        return SECTION_RE.sub(section, text, count=1)
    return text.rstrip() + "\n\n" + section


def _legacy_ternary_phase_count(text: str) -> int:
    count = 0
    for match in re.finditer(r"(?mi)^CONSTITUENT\s+(?P<phase>\S+)\s+:(?P<body>.*?)!\s*$", text):
        phase = match.group("phase").upper()
        if phase.startswith("C15") or phase in {"FCC_A1", "BCC_A2", "HCP_A3", "LIQUID"}:
            continue
        tokens = set(re.findall(r"[A-Z][A-Z]?", match.group("body").upper()))
        if len(tokens) >= 3:
            count += 1
    return count


def _stage_updates(
    tdb_dir: Path,
    binaries: dict[tuple[str, str], BinaryEndmember],
    interactions: Sequence[TernaryInteraction],
) -> tuple[dict[Path, str], HigherOrderUpdatePlan]:
    supported = {element for pair in binaries for element in pair}
    staged: dict[Path, str] = {}
    phase_occurrences = 0
    existing_sections = 0
    legacy_phases = 0
    candidate_names: list[str] = []
    for path in sorted(tdb_dir.glob("*.tdb")):
        elements = {element.title() for element in path.stem.split("-")}
        if len(elements & supported) < 3:
            continue
        section, phase_count = render_higher_order_section(elements, binaries, interactions)
        if not phase_count:
            continue
        original = path.read_text(encoding="utf-8")
        existing_sections += int(bool(SECTION_RE.search(original)))
        legacy_phases += _legacy_ternary_phase_count(SECTION_RE.sub("", original))
        updated = _replace_or_append_section(original, section)
        if updated != original:
            staged[path] = updated
        phase_occurrences += phase_count
        candidate_names.append(path.name)

    source_counts = Counter(item.source_energy_source for item in interactions)
    plan = HigherOrderUpdatePlan(
        len(binaries),
        len(interactions),
        source_counts["DFT"],
        source_counts["ML"],
        len(candidate_names),
        phase_occurrences,
        existing_sections,
        legacy_phases,
        tuple(candidate_names),
    )
    return staged, plan


def plan_higher_order_tdb_update(
    *,
    tdb_dir: Path = DEFAULT_TDB_DIR,
    binary_path: Path = DEFAULT_BINARY_PATH,
    interaction_path: Path = DEFAULT_INTERACTION_PATH,
) -> HigherOrderUpdatePlan:
    """Return the complete impact of an update without writing any files."""
    binaries, interactions = load_higher_order_c15_data(binary_path, interaction_path)
    _staged, plan = _stage_updates(tdb_dir, binaries, interactions)
    return plan


def update_tdbs_with_higher_order_intermetallics(
    *,
    tdb_dir: Path = DEFAULT_TDB_DIR,
    binary_path: Path = DEFAULT_BINARY_PATH,
    interaction_path: Path = DEFAULT_INTERACTION_PATH,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    dry_run: bool = True,
) -> HigherOrderUpdateResult:
    """Add or refresh all applicable ternary C15 phases.

    The safe default is ``dry_run=True``.  A real update snapshots *every* TDB,
    not only the files expected to change, so pre-existing working-tree edits
    remain recoverable independently of Git.
    """
    binaries, interactions = load_higher_order_c15_data(binary_path, interaction_path)
    staged, plan = _stage_updates(tdb_dir, binaries, interactions)
    if dry_run:
        return HigherOrderUpdateResult(plan, 0, None)
    if not staged:
        return HigherOrderUpdateResult(plan, 0, None)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / timestamp
    suffix = 1
    while backup_dir.exists():
        backup_dir = backup_root / f"{timestamp}-{suffix}"
        suffix += 1
    files_backup = backup_dir / "tdb"
    files_backup.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(tdb_dir, files_backup)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "section_version": SECTION_VERSION,
        "binary_source": str(binary_path),
        "binary_source_sha256": _sha256(binary_path),
        "interaction_source": str(interaction_path),
        "interaction_source_sha256": _sha256(interaction_path),
        "plan": {
            "source_binary_count": plan.source_binary_count,
            "source_interaction_count": plan.source_interaction_count,
            "source_dft_count": plan.source_dft_count,
            "source_ml_count": plan.source_ml_count,
            "affected_files": plan.affected_files,
            "generated_phase_occurrences": plan.generated_phase_occurrences,
            "preserved_legacy_ternary_phases": plan.preserved_legacy_ternary_phases,
            "files": list(plan.files),
        },
    }
    _atomic_write(backup_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")

    try:
        for path, updated in staged.items():
            _atomic_write(path, updated)
    except Exception:
        for path in staged:
            shutil.copy2(files_backup / path.name, path)
        raise
    return HigherOrderUpdateResult(plan, len(staged), backup_dir)


def remove_higher_order_intermetallic_sections(
    *,
    tdb_dir: Path = DEFAULT_TDB_DIR,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    dry_run: bool = True,
) -> HigherOrderRemovalResult:
    """Remove only updater-owned C15 sections, preserving all surrounding text.

    As with insertion, the safe default is a read-only dry run. A real removal
    snapshots the complete current TDB directory first and rolls back changed
    files if any write fails.
    """
    staged: dict[Path, str] = {}
    removed_sections = 0
    for path in sorted(tdb_dir.glob("*.tdb")):
        original = path.read_text(encoding="utf-8")
        updated, count = SECTION_RE.subn("", original)
        if not count:
            continue
        if count != 1:
            raise HigherOrderTDBError(f"Multiple generated sections found in {path.name}")
        staged[path] = updated.rstrip() + "\n"
        removed_sections += count

    if dry_run or not staged:
        return HigherOrderRemovalResult(0 if dry_run else len(staged), removed_sections, None)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / f"before-removal-{timestamp}"
    suffix = 1
    while backup_dir.exists():
        backup_dir = backup_root / f"before-removal-{timestamp}-{suffix}"
        suffix += 1
    files_backup = backup_dir / "tdb"
    files_backup.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(tdb_dir, files_backup)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operation": "remove_higher_order_intermetallic_sections",
        "changed_files": len(staged),
        "removed_sections": removed_sections,
        "files": [path.name for path in staged],
    }
    _atomic_write(backup_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")

    try:
        for path, updated in staged.items():
            _atomic_write(path, updated)
    except Exception:
        for path in staged:
            shutil.copy2(files_backup / path.name, path)
        raise
    return HigherOrderRemovalResult(len(staged), removed_sections, backup_dir)
