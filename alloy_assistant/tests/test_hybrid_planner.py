"""Tests for constrained LLM planning and deterministic safeguards."""

from __future__ import annotations

import unittest

from alloy_assistant.src.hybrid_planner import plan_question_hybrid


class FakePlanningModel:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def plan_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_names: tuple[str, ...],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "tool_names": tool_names,
            }
        )
        return self.payload


class HybridPlannerTest(unittest.TestCase):
    def test_exact_sql_question_keeps_deterministic_fast_path(self) -> None:
        model = FakePlanningModel({})
        plan = plan_question_hybrid(
            "What is the PMR of MoNbTaW at 1000 K?",
            model,
        )
        self.assertEqual(model.calls, [])
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            ["get_pmr_for_system"],
        )
        self.assertIn("planner:deterministic_fast_path", plan.signals)

    def test_candidate_assessment_gets_complete_evidence_checklist(self) -> None:
        model = FakePlanningModel(
            {
                "tool_calls": [
                    {
                        "tool_name": "hybrid_search",
                        "arguments_json": (
                            '{"query":"Why is TaVWZr a good candidate?"}'
                        ),
                        "reason": "Retrieve narrative context.",
                    }
                ],
                "coverage_notes": [],
            }
        )
        plan = plan_question_hybrid(
            "Why do you think alloy system TaVWZr is a good candidate?",
            model,
        )
        names = [call.tool_name for call in plan.tool_calls]
        self.assertEqual(
            names,
            [
                "get_system_overview",
                "get_pmr_for_system",
                "get_miscibility_predictions_for_system",
                "get_pairwise_interactions_for_system",
                "get_experimental_observations_for_system",
                "hybrid_search",
            ],
        )
        self.assertEqual(plan.routes, ("sql", "documents"))
        self.assertEqual(plan.extracted_system, "Ta-V-W-Zr")
        self.assertIn("planner:llm", plan.signals)
        self.assertFalse(plan.needs_clarification)

    def test_extracted_system_overrides_model_arguments(self) -> None:
        model = FakePlanningModel(
            {
                "tool_calls": [
                    {
                        "tool_name": "get_pmr_for_system",
                        "arguments_json": '{"system_name":"Mo-Nb-Ta-W"}',
                        "reason": "Retrieve a numerical profile.",
                    },
                    {
                        "tool_name": "hybrid_search",
                        "arguments_json": '{"query":"different question"}',
                        "reason": "Retrieve context.",
                    },
                ],
                "coverage_notes": [],
            }
        )
        plan = plan_question_hybrid(
            "Tell me about the PMR behavior of TaVWZr.",
            model,
        )
        for call in plan.tool_calls:
            if "system_name" in call.arguments:
                self.assertEqual(call.arguments["system_name"], "Ta-V-W-Zr")
            if "query" in call.arguments:
                self.assertEqual(call.arguments["query"], plan.question)

    def test_llm_cannot_drop_explicit_structured_evidence(self) -> None:
        model = FakePlanningModel(
            {
                "tool_calls": [
                    {
                        "tool_name": "hybrid_search",
                        "arguments_json": "{}",
                        "reason": "Retrieve context.",
                    }
                ],
                "coverage_notes": [],
            }
        )
        plan = plan_question_hybrid(
            "What is the PMR of MoNbTaW at 1000 K, and why is it high?",
            model,
        )
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            ["get_pmr_for_system", "hybrid_search"],
        )

    def test_invalid_llm_plan_falls_back_to_candidate_checklist(self) -> None:
        model = FakePlanningModel(
            {
                "tool_calls": [
                    {
                        "tool_name": "write_arbitrary_sql",
                        "arguments_json": "{}",
                        "reason": "Unsafe invented tool.",
                    }
                ],
                "coverage_notes": [],
            }
        )
        plan = plan_question_hybrid(
            "Is TaVWZr a promising candidate?",
            model,
        )
        self.assertIn("planner:deterministic_fallback", plan.signals)
        self.assertIn(
            "get_pairwise_interactions_for_system",
            {call.tool_name for call in plan.tool_calls},
        )
        self.assertEqual(plan.routes, ("sql", "documents"))

    def test_invalid_non_candidate_plan_uses_existing_router(self) -> None:
        model = FakePlanningModel({"tool_calls": "invalid"})
        plan = plan_question_hybrid(
            "What is the PMR of MoNbTaW at 1000 K, and why is it high?",
            model,
        )
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            ["get_pmr_for_system", "hybrid_search"],
        )
        self.assertIn("planner:deterministic_fallback", plan.signals)


if __name__ == "__main__":
    unittest.main()
