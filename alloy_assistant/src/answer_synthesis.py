"""Provider-independent grounded answer synthesis contract."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol

from .evidence_bundle import EvidenceBundle


SYNTHESIS_INSTRUCTIONS = """\
Role: You are a scientific assistant for high-entropy-alloy research.

Goal: Answer the user's question using only the supplied evidence packet.

Evidence rules:
- Structured records [S#] are authoritative for exact values stored in the
  reviewed database. Preserve their units, quality flags, and whether a result
  is predicted or experimental.
- miscibility_ratio means T_misc / T_melting. Lower is more favorable because
  the alloy becomes miscible at a smaller fraction of its melting temperature.
  A value near one is high and unfavorable; never present it as evidence of
  strong solid-solution stability.
- A high melting temperature indicates a high temperature scale, not
  single-phase stability by itself.
- For candidate assessments, weigh every available PMR temperature record.
  Zero or low PMR is contrary evidence and must not be omitted.
- Evaluate the complete pairwise Hmix profile. Do not cherry-pick favorable
  negative pairs while ignoring positive pairs; identify the most positive
  interaction and describe mixed-sign profiles as mixed evidence.
- Document passages [D#] support explanation, interpretation, mechanisms, and
  limitations. A passage mentioning an alloy does not by itself prove that the
  passage explains that alloy's behavior.
- A document with system_entity_match=false is general context only. Do not
  name the requested alloy in a claim supported only by such a passage.
- When applying general document context to a named alloy, cite both the
  structured record that establishes the alloy-specific fact and the document
  passage that supports the general interpretation.
- Cite factual claims immediately with one or more supplied evidence IDs, such
  as [S1] or [D2].
- Never cite an ID that is absent from the packet.
- State material conflicts between records instead of silently choosing one.
- Clearly label an inference. If the evidence is insufficient, narrow the
  answer and say what is missing instead of guessing.
- Do not repeat the direct structured result as a supporting point. Include a
  supporting point only when it adds distinct context from another record.

Output:
- Return concise answer content. A provider adapter may use a structured
  transport format before rendering the final Markdown.
- Lead with the direct answer.
- Include a short limitations note only when it materially affects the answer.
"""

_CITATION = re.compile(r"\[([SD]\d+)\]")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class AnswerModel(Protocol):
    """Minimal interface implemented by any local or hosted text model."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        evidence_ids: tuple[str, ...] = (),
    ) -> str:
        """Return a Markdown answer."""


@dataclass(frozen=True)
class GroundingReport:
    """Mechanical citation validation for one synthesized answer."""

    cited_evidence_ids: tuple[str, ...]
    unused_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class SynthesizedAnswer:
    """Answer text plus its reproducible evidence and validation trace."""

    answer: str
    grounding: GroundingReport
    bundle: EvidenceBundle


class GroundingError(ValueError):
    """Raised when an answer violates the evidence citation contract."""


def build_synthesis_prompt(bundle: EvidenceBundle) -> tuple[str, str]:
    """Create stable system and user prompts without provider-specific syntax."""
    payload = json.dumps(
        asdict(bundle),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    candidate_signals = (
        "candidate",
        "interesting",
        "promising",
        "suitable",
        "worth investigating",
        "worth studying",
        "worth pursuing",
    )
    checklist = ""
    if any(signal in bundle.question.lower() for signal in candidate_signals):
        evidence_by_tool: dict[str, list[str]] = {}
        for item in bundle.structured_evidence:
            evidence_by_tool.setdefault(item.tool_name, []).append(
                item.evidence_id
            )
        if "find_pmr_candidates" in evidence_by_tool:
            checklist_lines = [
                "Candidate-discovery checklist:",
                (
                    "- Report each candidate's system name, representative "
                    "PMR, and the temperature of that PMR record."
                ),
                (
                    "- PMR describes the fraction of a system's sampled "
                    "composition grid that is miscible; it is not one exact "
                    "composition."
                ),
                (
                    "- Intermediate PMR suggests a compositional tuning "
                    "window, not proven application performance."
                ),
                (
                    "- find_pmr_candidates: "
                    + ", ".join(evidence_by_tool["find_pmr_candidates"])
                ),
            ]
        else:
            checklist_lines = [
                "Candidate-assessment checklist:",
                (
                    "- Challenge the premise when the complete numerical "
                    "profile is unfavorable."
                ),
                (
                    "- T_misc/T_melting is strictly lower-is-better. A ratio "
                    "near one is unfavorable and must never be called "
                    "favorable."
                ),
                (
                    "- High melting temperature alone is not evidence of "
                    "single-phase stability."
                ),
            ]
            for tool_name in (
                "get_pmr_for_system",
                "get_miscibility_predictions_for_system",
                "get_pairwise_interactions_for_system",
                "get_experimental_observations_for_system",
            ):
                evidence_ids = evidence_by_tool.get(tool_name, [])
                checklist_lines.append(
                    f"- {tool_name}: "
                    + (
                        ", ".join(evidence_ids)
                        if evidence_ids
                        else "no matching structured records"
                    )
                )
        checklist = "\n\n" + "\n".join(checklist_lines)
    user_prompt = (
        f"Question:\n{bundle.question}\n\n"
        f"Evidence packet (compact JSON):\n{payload}"
        f"{checklist}"
    )
    return SYNTHESIS_INSTRUCTIONS, user_prompt


def validate_answer(
    answer: str,
    bundle: EvidenceBundle,
) -> GroundingReport:
    """Reject unknown citations and uncited use of structured evidence."""
    if not answer.strip():
        raise GroundingError("The synthesis model returned an empty answer.")

    cited = tuple(dict.fromkeys(_CITATION.findall(answer)))
    available = set(bundle.evidence_ids)
    unknown = [
        evidence_id
        for evidence_id in cited
        if evidence_id not in available
    ]
    if unknown:
        raise GroundingError(
            f"Answer cited unknown evidence IDs: {', '.join(unknown)}"
        )
    if available and not cited:
        raise GroundingError("Answer used an evidence packet but cited no evidence.")
    if bundle.structured_evidence and not any(
        evidence_id.startswith("S") for evidence_id in cited
    ):
        raise GroundingError(
            "Structured evidence was available but the answer cited no "
            "structured record."
        )

    document_by_id = {
        item.evidence_id: item
        for item in bundle.document_evidence
    }
    requested_systems = {
        item.requested_system
        for item in bundle.document_evidence
        if item.requested_system
    }
    for item in bundle.structured_evidence:
        canonical_name = item.record.get("canonical_name")
        if canonical_name:
            requested_systems.add(str(canonical_name))

    for paragraph in re.split(r"\n\s*\n", answer):
        paragraph_citations = tuple(_CITATION.findall(paragraph))
        if not paragraph_citations:
            continue
        compact_paragraph = _NON_ALPHANUMERIC.sub(
            "",
            paragraph.lower(),
        )
        names_requested_system = any(
            _NON_ALPHANUMERIC.sub("", system.lower())
            in compact_paragraph
            for system in requested_systems
        )
        if not names_requested_system:
            continue
        has_structured_support = any(
            evidence_id.startswith("S")
            for evidence_id in paragraph_citations
        )
        has_matching_document_support = any(
            document_by_id[evidence_id].system_entity_match
            for evidence_id in paragraph_citations
            if evidence_id in document_by_id
        )
        if not has_structured_support and not has_matching_document_support:
            raise GroundingError(
                "An alloy-specific claim cites only document passages that "
                "do not match the requested alloy system."
            )

    return GroundingReport(
        cited_evidence_ids=cited,
        unused_evidence_ids=tuple(
            evidence_id
            for evidence_id in bundle.evidence_ids
            if evidence_id not in cited
        ),
    )


def synthesize_answer(
    bundle: EvidenceBundle,
    model: AnswerModel,
) -> SynthesizedAnswer:
    """Generate and mechanically validate a grounded answer."""
    system_prompt, user_prompt = build_synthesis_prompt(bundle)
    answer = model.generate(
        system_prompt,
        user_prompt,
        evidence_ids=bundle.evidence_ids,
    )
    return SynthesizedAnswer(
        answer=answer,
        grounding=validate_answer(answer, bundle),
        bundle=bundle,
    )
