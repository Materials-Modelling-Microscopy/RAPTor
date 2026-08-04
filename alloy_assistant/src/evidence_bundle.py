"""Assemble reviewed tool results into a bounded synthesis evidence packet."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from .database import DEFAULT_DATABASE_PATH, connect
from .route_question import QuestionRoutePlan, plan_question
from .tool_executor import ToolExecutionResult, execute_plan


@dataclass(frozen=True)
class StructuredEvidence:
    """One structured database record available to answer synthesis."""

    evidence_id: str
    tool_name: str
    arguments: dict[str, object]
    record: dict[str, object]


@dataclass(frozen=True)
class DocumentEvidence:
    """One citation-ready document passage available to answer synthesis."""

    evidence_id: str
    tool_name: str
    citation: str
    title: str
    page_start: int
    page_end: int
    section_title: str | None
    text: str
    source_id: str
    chunk_id: str
    source_class: str
    authority_status: str
    hybrid_score: float
    requested_system: str | None
    system_entity_match: bool


@dataclass(frozen=True)
class EvidenceBundle:
    """Complete, serializable handoff from retrieval to answer synthesis."""

    question: str
    routes: tuple[str, ...]
    structured_coverage: str
    structured_evidence: tuple[StructuredEvidence, ...]
    document_evidence: tuple[DocumentEvidence, ...]
    warnings: tuple[str, ...]

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        """Return every identifier that a synthesized answer may cite."""
        return tuple(
            item.evidence_id
            for item in (
                *self.structured_evidence,
                *self.document_evidence,
            )
        )


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {
            key: _plain(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {
            str(key): _plain(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _records(value: object) -> list[dict[str, object]]:
    plain = _plain(value)
    if plain is None:
        return []
    values = plain if isinstance(plain, list) else [plain]
    return [
        item if isinstance(item, dict) else {"value": item}
        for item in values
    ]


def build_evidence_bundle(
    plan: QuestionRoutePlan,
    results: list[ToolExecutionResult],
    *,
    max_structured_records: int = 200,
) -> EvidenceBundle:
    """Normalize SQL and document results into stable, citable evidence IDs."""
    if max_structured_records < 1:
        raise ValueError("max_structured_records must be positive")

    structured: list[StructuredEvidence] = []
    documents: list[DocumentEvidence] = []
    warnings: list[str] = []
    structured_seen = 0

    for result in results:
        records = _records(result.value)
        if not records:
            warnings.append(
                f"{result.tool_name} returned no matching records."
            )
        if result.route == "documents":
            for record in records:
                documents.append(
                    DocumentEvidence(
                        evidence_id=f"D{len(documents) + 1}",
                        tool_name=result.tool_name,
                        citation=str(record["citation"]),
                        title=str(record["title"]),
                        page_start=int(record["page_start"]),
                        page_end=int(record["page_end"]),
                        section_title=(
                            None
                            if record.get("section_title") is None
                            else str(record["section_title"])
                        ),
                        text=str(record["chunk_text"]),
                        source_id=str(record["source_id"]),
                        chunk_id=str(record["chunk_id"]),
                        source_class=str(record["source_class"]),
                        authority_status=str(record["authority_status"]),
                        hybrid_score=float(record["hybrid_score"]),
                        requested_system=(
                            None
                            if record.get("requested_system") is None
                            else str(record["requested_system"])
                        ),
                        system_entity_match=bool(
                            record.get("system_entity_match", False)
                        ),
                    )
                )
            continue

        for record in records:
            structured_seen += 1
            if len(structured) >= max_structured_records:
                continue
            structured.append(
                StructuredEvidence(
                    evidence_id=f"S{len(structured) + 1}",
                    tool_name=result.tool_name,
                    arguments=dict(result.arguments),
                    record=record,
                )
            )

    if structured_seen > len(structured):
        warnings.append(
            "Structured evidence was truncated from "
            f"{structured_seen} to {len(structured)} records."
        )
    if any(result.route == "sql" for result in results) and not structured:
        warnings.append("The structured tools returned no matching records.")
    if any(result.route == "documents" for result in results) and not documents:
        warnings.append("Document retrieval returned no passages.")

    return EvidenceBundle(
        question=plan.question,
        routes=plan.routes,
        structured_coverage=plan.structured_coverage,
        structured_evidence=tuple(structured),
        document_evidence=tuple(documents),
        warnings=tuple(warnings),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the evidence packet used for grounded synthesis.",
    )
    parser.add_argument("question")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument("--max-structured-records", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")
    plan = plan_question(args.question)
    with connect(database_path, read_only=True) as connection:
        results = execute_plan(connection, plan)
    bundle = build_evidence_bundle(
        plan,
        results,
        max_structured_records=args.max_structured_records,
    )
    print(json.dumps(asdict(bundle), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
