"""Read-only experimental evidence for the alloy-system summary page."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

import pandas as pd

from alloy_assistant.src.database import DEFAULT_DATABASE_PATH, connect
from alloy_assistant.src.normalization import parse_composition_formula
from alloy_assistant.src.queries import get_experimental_observations_for_system


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CITATION_PATH = ROOT / "alloy_web" / "data" / "experimental_citations.json"
DEFAULT_EXPERIMENTAL_SOURCE_PATH = (
    ROOT
    / "alloy_assistant"
    / "data"
    / "inbox"
    / "experimental_validation"
    / "refractory_hea_validation.csv"
)
_SOURCE_ROW_PATTERN = re.compile(r"^csv-row:(\d+)$")
_SAMPLE_ROW_SUFFIX = re.compile(r"\s+row\s+\d+$")


@dataclass(frozen=True)
class ExperimentalEvidence:
    """Experimental observations and their manuscript citations."""

    observations: pd.DataFrame
    citations: pd.DataFrame
    database_available: bool


def _empty_evidence(*, database_available: bool) -> ExperimentalEvidence:
    return ExperimentalEvidence(
        observations=pd.DataFrame(
            columns=[
                "Composition",
                "Reported phases",
                "Processing method",
                "Processing temperature (K)",
                "Reference",
            ]
        ),
        citations=pd.DataFrame(columns=["Reference", "Citation"]),
        database_available=database_available,
    )


def load_citation_catalog(path: Path = DEFAULT_CITATION_PATH) -> dict:
    """Load and validate the manuscript-derived row-to-citation catalog."""
    with path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    row_references = catalog.get("reference_numbers")
    references = catalog.get("references")
    first_source_row = catalog.get("first_source_row")
    if not isinstance(first_source_row, int) or first_source_row < 1:
        raise ValueError("Experimental citation catalog has an invalid first source row")
    if not isinstance(row_references, list) or len(row_references) != 109:
        raise ValueError("Experimental citation catalog must map all 109 records")
    if not isinstance(references, dict) or set(references) != {
        str(index) for index in range(1, 55)
    }:
        raise ValueError("Experimental citation catalog must contain references 1–54")
    missing = [number for number in row_references if str(number) not in references]
    if missing:
        raise ValueError(f"Experimental citation catalog has unmapped references: {missing}")
    return catalog


def _source_row(source_locator: str | None) -> int:
    match = _SOURCE_ROW_PATTERN.fullmatch(source_locator or "")
    if match is None:
        raise ValueError(f"Unsupported experimental source locator: {source_locator!r}")
    return int(match.group(1))


def _reference_for_source_row(source_row: int, catalog: dict) -> int:
    offset = source_row - int(catalog["first_source_row"])
    row_references = catalog["reference_numbers"]
    if offset < 0 or offset >= len(row_references):
        raise ValueError(
            f"Experimental source row {source_row} has no manuscript citation mapping"
        )
    return int(row_references[offset])


def _display_composition(sample_label: str | None, fallback: str) -> str:
    """Recover the manuscript formula retained in the sample label."""
    if sample_label:
        formula = _SAMPLE_ROW_SUFFIX.sub("", sample_label).strip()
        if formula:
            return formula
    return fallback


def _optional_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value).strip() or None


def _source_file_evidence(
    alloy_system: list[str] | tuple[str, ...],
    *,
    source_path: Path,
    catalog: dict,
) -> ExperimentalEvidence:
    """Read the approved source CSV when the generated DuckDB is unavailable."""
    if not source_path.is_file():
        return _empty_evidence(database_available=False)

    source = pd.read_csv(source_path, encoding="utf-8-sig")
    required = {
        "Composition",
        "Expt. Reported Phases",
        "Processing",
        "Processing. Temp",
    }
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(
            "Experimental source is missing required columns: "
            + ", ".join(sorted(missing))
        )
    if source["Composition"].notna().sum() != len(catalog["reference_numbers"]):
        raise ValueError(
            "Experimental source and citation catalog contain different record counts"
        )

    requested_elements = frozenset(alloy_system)
    records: list[dict[str, object]] = []
    used_references: set[int] = set()
    for frame_index, row in source.iterrows():
        formula = _optional_text(row["Composition"])
        if formula is None:
            continue
        if frozenset(parse_composition_formula(formula)) != requested_elements:
            continue

        source_row = int(frame_index) + 2
        reference_number = _reference_for_source_row(source_row, catalog)
        used_references.add(reference_number)
        processing_temperature = row["Processing. Temp"]
        records.append(
            {
                "Composition": formula,
                "Reported phases": _optional_text(row["Expt. Reported Phases"]),
                "Processing method": _optional_text(row["Processing"]),
                "Processing temperature (K)": (
                    None
                    if pd.isna(processing_temperature)
                    else float(processing_temperature)
                ),
                "Reference": f"[{reference_number}]",
            }
        )

    if not records:
        return _empty_evidence(database_available=False)

    return ExperimentalEvidence(
        observations=pd.DataFrame(records),
        citations=pd.DataFrame(
            [
                {
                    "Reference": f"[{reference_number}]",
                    "Citation": catalog["references"][str(reference_number)],
                }
                for reference_number in sorted(used_references)
            ]
        ),
        database_available=False,
    )


def load_experimental_evidence(
    alloy_system: list[str] | tuple[str, ...],
    *,
    database_path: Path = DEFAULT_DATABASE_PATH,
    citation_path: Path = DEFAULT_CITATION_PATH,
    source_path: Path = DEFAULT_EXPERIMENTAL_SOURCE_PATH,
) -> ExperimentalEvidence:
    """Return exact-system experimental records without modifying the database.

    The Alloy Assistant remains the source of experimental observations. The
    supplied manuscript catalog only supplies the publication reference that
    belongs to each existing ``csv-row`` source locator.
    """
    database_path = Path(database_path)
    catalog = load_citation_catalog(citation_path)
    if not database_path.is_file():
        return _source_file_evidence(
            alloy_system,
            source_path=Path(source_path),
            catalog=catalog,
        )

    system_name = "-".join(alloy_system)
    with connect(database_path, read_only=True) as connection:
        observations = get_experimental_observations_for_system(
            connection,
            system_name,
        )
    if not observations:
        return _empty_evidence(database_available=True)

    records: list[dict[str, object]] = []
    used_references: set[int] = set()
    for observation in observations:
        source_row = _source_row(observation.source_locator)
        reference_number = _reference_for_source_row(source_row, catalog)
        used_references.add(reference_number)
        records.append(
            {
                "_source_row": source_row,
                "Composition": _display_composition(
                    observation.sample_label,
                    observation.original_formula or observation.canonical_formula,
                ),
                "Reported phases": observation.raw_phase_label,
                "Processing method": observation.processing_route,
                "Processing temperature (K)": observation.processing_temperature_K,
                "Reference": f"[{reference_number}]",
            }
        )

    records.sort(key=lambda record: int(record["_source_row"]))
    observation_frame = pd.DataFrame(records).drop(columns=["_source_row"])
    citation_frame = pd.DataFrame(
        [
            {
                "Reference": f"[{reference_number}]",
                "Citation": catalog["references"][str(reference_number)],
            }
            for reference_number in sorted(used_references)
        ]
    )
    return ExperimentalEvidence(
        observations=observation_frame,
        citations=citation_frame,
        database_available=True,
    )
