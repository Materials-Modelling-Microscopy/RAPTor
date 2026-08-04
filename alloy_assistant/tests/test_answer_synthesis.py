"""Tests for the retrieval-to-synthesis evidence contract."""

from __future__ import annotations

import unittest
from dataclasses import replace

from alloy_assistant.src.answer_synthesis import (
    GroundingError,
    build_synthesis_prompt,
    synthesize_answer,
    validate_answer,
)
from alloy_assistant.src.evidence_bundle import build_evidence_bundle
from alloy_assistant.src.hybrid_retrieval import HybridChunkMatch
from alloy_assistant.src.queries import PmrPrediction
from alloy_assistant.src.route_question import plan_question
from alloy_assistant.src.tool_executor import ToolExecutionResult


class FakeAnswerModel:
    """Return a fixed response while retaining the received prompts."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.system_prompt = ""
        self.user_prompt = ""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        evidence_ids: tuple[str, ...] = (),
    ) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.evidence_ids = evidence_ids
        return self.answer


class AnswerSynthesisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan_question(
            "What is the PMR of MoNbTaW at 1000 K, and why is it high?"
        )
        pmr = PmrPrediction(
            canonical_name="Mo-Nb-Ta-W",
            temperature_K=1000.0,
            pmr_percent=100.0,
            grid_spacing_atomic_fraction=0.1,
            quality_flag="validated",
            model_name="test",
            model_version="test",
            source_id="source_table",
            source_row_number=6,
        )
        passage = HybridChunkMatch(
            rank=1,
            title="Dissertation",
            citation="Dissertation, p. 63",
            page_start=63,
            page_end=63,
            section_title="Results",
            chunk_text="Mo-Nb-Ta-W has a large predicted miscible region.",
            hybrid_score=0.03,
            retrieval_channels="lexical+semantic",
            lexical_rank=1,
            lexical_score=3,
            semantic_rank=2,
            cosine_similarity=0.8,
            authority_status="authoritative",
            authority_weight=1.05,
            requested_system="Mo-Nb-Ta-W",
            system_entity_match=True,
            system_entity_weight=1.2,
            source_class="manuscript",
            source_id="source_document",
            chunk_id="chunk_1",
        )
        self.results = [
            ToolExecutionResult(
                tool_name="get_pmr_for_system",
                route="sql",
                arguments={
                    "system_name": "Mo-Nb-Ta-W",
                    "temperature_K": 1000.0,
                },
                value=[pmr],
            ),
            ToolExecutionResult(
                tool_name="hybrid_search",
                route="documents",
                arguments={"query": self.plan.question},
                value=[passage],
            ),
        ]
        self.bundle = build_evidence_bundle(self.plan, self.results)

    def test_bundle_separates_structured_and_document_evidence(self) -> None:
        self.assertEqual(self.bundle.evidence_ids, ("S1", "D1"))
        self.assertEqual(
            self.bundle.structured_evidence[0].record["pmr_percent"],
            100.0,
        )
        self.assertEqual(
            self.bundle.document_evidence[0].citation,
            "Dissertation, p. 63",
        )

    def test_prompt_contains_question_rules_and_packet(self) -> None:
        system_prompt, user_prompt = build_synthesis_prompt(self.bundle)
        self.assertIn("using only the supplied evidence", system_prompt)
        self.assertIn("Lower is more favorable", system_prompt)
        self.assertIn(self.plan.question, user_prompt)
        self.assertIn('"evidence_id":"S1"', user_prompt)
        self.assertIn('"evidence_id":"D1"', user_prompt)

    def test_candidate_prompt_lists_required_evidence_categories(self) -> None:
        candidate_bundle = replace(
            self.bundle,
            question="Why is MoNbTaW a promising candidate?",
        )
        _, user_prompt = build_synthesis_prompt(candidate_bundle)
        self.assertIn("Candidate-assessment checklist", user_prompt)
        self.assertIn("strictly lower-is-better", user_prompt)
        self.assertIn("get_pmr_for_system: S1", user_prompt)
        self.assertIn(
            "get_experimental_observations_for_system: "
            "no matching structured records",
            user_prompt,
        )

    def test_global_candidate_prompt_uses_discovery_semantics(self) -> None:
        candidate_record = replace(
            self.bundle.structured_evidence[0],
            tool_name="find_pmr_candidates",
        )
        candidate_bundle = replace(
            self.bundle,
            question="Give me promising quinary tuning candidates.",
            structured_evidence=(candidate_record,),
        )
        _, user_prompt = build_synthesis_prompt(candidate_bundle)
        self.assertIn("Candidate-discovery checklist", user_prompt)
        self.assertIn("not one exact composition", user_prompt)
        self.assertNotIn("Candidate-assessment checklist", user_prompt)

    def test_unknown_citation_is_rejected(self) -> None:
        with self.assertRaisesRegex(GroundingError, "unknown evidence"):
            validate_answer("The PMR is 100% [S9].", self.bundle)

    def test_structured_result_must_be_cited(self) -> None:
        with self.assertRaisesRegex(GroundingError, "structured record"):
            validate_answer("The system is stable [D1].", self.bundle)

    def test_model_interface_produces_validated_answer(self) -> None:
        model = FakeAnswerModel(
            "The predicted PMR is 100% at 1000 K [S1]. "
            "The dissertation also identifies a large miscible region [D1]."
        )
        result = synthesize_answer(self.bundle, model)
        self.assertEqual(result.grounding.cited_evidence_ids, ("S1", "D1"))
        self.assertIn("Evidence packet", model.user_prompt)
        self.assertEqual(model.evidence_ids, ("S1", "D1"))

    def test_unmatched_document_cannot_support_system_specific_claim(self) -> None:
        unmatched_document = replace(
            self.bundle.document_evidence[0],
            system_entity_match=False,
        )
        document_only_bundle = replace(
            self.bundle,
            structured_evidence=(),
            document_evidence=(unmatched_document,),
        )
        with self.assertRaisesRegex(GroundingError, "alloy-specific claim"):
            validate_answer(
                "MoNbTaW is nearly completely miscible above 800 K [D1].",
                document_only_bundle,
            )

    def test_unmatched_document_can_support_general_context(self) -> None:
        unmatched_document = replace(
            self.bundle.document_evidence[0],
            system_entity_match=False,
        )
        document_only_bundle = replace(
            self.bundle,
            structured_evidence=(),
            document_evidence=(unmatched_document,),
        )
        report = validate_answer(
            "High-range PMR generally indicates compositional tolerance [D1].",
            document_only_bundle,
        )
        self.assertEqual(report.cited_evidence_ids, ("D1",))

    def test_structured_records_are_bounded(self) -> None:
        bundle = build_evidence_bundle(
            self.plan,
            [self.results[0]],
            max_structured_records=1,
        )
        self.assertEqual(len(bundle.structured_evidence), 1)


if __name__ == "__main__":
    unittest.main()
