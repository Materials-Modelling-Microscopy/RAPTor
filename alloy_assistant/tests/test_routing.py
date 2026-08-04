"""Tests for the transparent question router and reviewed tool registry."""

from __future__ import annotations

import unittest

from alloy_assistant.src.route_question import plan_question
from alloy_assistant.src.tool_registry import TOOL_REGISTRY, get_tool_spec


class QuestionRoutingTest(unittest.TestCase):
    """Cover SQL-only, document-only, combined, and missing-tool paths."""

    def test_exact_pmr_routes_to_sql_with_extracted_arguments(self) -> None:
        plan = plan_question("What is the PMR of MoNbTaW at 1000 K?")
        self.assertEqual(plan.routes, ("sql",))
        self.assertEqual(plan.extracted_system, "Mo-Nb-Ta-W")
        self.assertEqual(plan.extracted_temperature_K, 1000.0)
        self.assertEqual(plan.structured_coverage, "covered")
        call = plan.tool_calls[0]
        self.assertEqual(call.tool_name, "get_pmr_for_system")
        self.assertEqual(call.arguments["temperature_K"], 1000.0)
        self.assertFalse(plan.needs_clarification)

    def test_explanation_routes_to_documents(self) -> None:
        plan = plan_question(
            "Why is MoNbTaW considered a robust solid-solution system?"
        )
        self.assertEqual(plan.routes, ("documents",))
        self.assertEqual(plan.tool_calls[0].tool_name, "hybrid_search")
        self.assertEqual(plan.structured_coverage, "not_requested")

    def test_mixed_question_routes_to_both(self) -> None:
        plan = plan_question(
            "What is the PMR of MoNbTaW at 1000 K, and why is it high?"
        )
        self.assertEqual(plan.routes, ("sql", "documents"))
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            ["get_pmr_for_system", "hybrid_search"],
        )

    def test_what_is_known_routes_value_and_documents(self) -> None:
        plan = plan_question(
            "What is the miscibility temperature of TaTiVW, "
            "and what is known about it?"
        )
        self.assertEqual(plan.extracted_system, "Ta-Ti-V-W")
        self.assertEqual(plan.routes, ("sql", "documents"))
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            [
                "get_miscibility_predictions_for_system",
                "hybrid_search",
            ],
        )

    def test_prediction_experiment_comparison_composes_tools(self) -> None:
        plan = plan_question(
            "Compare predicted phases with experimental observations "
            "for MoNbTaW."
        )
        self.assertEqual(plan.routes, ("sql", "documents"))
        self.assertEqual(
            {call.tool_name for call in plan.tool_calls},
            {
                "get_predicted_phases_for_system",
                "get_experimental_observations_for_system",
                "hybrid_search",
            },
        )

    def test_component_words_are_not_substring_matched(self) -> None:
        plan = plan_question(
            "Which quaternary system has the highest T_misc?"
        )
        call = plan.tool_calls[0]
        self.assertEqual(
            call.tool_name,
            "rank_equimolar_miscibility_predictions",
        )
        self.assertEqual(call.arguments["n_components"], 4)

    def test_known_structured_gap_is_reported_not_improvised(self) -> None:
        plan = plan_question("Which system has the highest PMR at 1000 K?")
        self.assertEqual(plan.structured_coverage, "unsupported")
        self.assertTrue(plan.needs_clarification)
        self.assertEqual(plan.tool_calls, ())
        self.assertIn("sql", plan.routes)
        self.assertTrue(plan.coverage_notes)

    def test_mid_pmr_quaternary_routes_to_candidate_search(self) -> None:
        plan = plan_question("Give me some mid-PMR quaternary compositions.")
        self.assertEqual(plan.routes, ("sql",))
        call = plan.tool_calls[0]
        self.assertEqual(call.tool_name, "find_pmr_candidates")
        self.assertEqual(call.arguments["n_components"], 4)
        self.assertEqual(call.arguments["target_pmr_percent"], 50.0)
        self.assertEqual(call.arguments["tolerance_percent"], 25.0)
        self.assertFalse(plan.needs_clarification)

    def test_compositional_tuning_uses_pmr_and_documents(self) -> None:
        plan = plan_question(
            "What are some quinary candidates that would make for "
            "good compositional tuning?"
        )
        self.assertEqual(plan.routes, ("sql", "documents"))
        self.assertEqual(
            [call.tool_name for call in plan.tool_calls],
            ["find_pmr_candidates", "hybrid_search"],
        )
        self.assertEqual(plan.tool_calls[0].arguments["n_components"], 5)

    def test_missing_required_entity_is_explicit(self) -> None:
        plan = plan_question("What is the miscibility temperature?")
        self.assertTrue(plan.needs_clarification)
        self.assertEqual(
            plan.tool_calls[0].missing_arguments,
            ("system_name",),
        )

    def test_binary_threshold_and_room_temperature_tools(self) -> None:
        threshold = plan_question(
            "Which binaries have T_misc above 3500 K?"
        )
        self.assertEqual(
            threshold.tool_calls[0].tool_name,
            "find_binaries_above_miscibility_temperature",
        )
        room = plan_question(
            "Which binaries are stable at room temperature?"
        )
        self.assertEqual(
            room.tool_calls[0].tool_name,
            "find_room_temperature_stable_binaries",
        )

    def test_registry_rejects_invented_tools(self) -> None:
        self.assertIn("get_pmr_for_system", TOOL_REGISTRY)
        with self.assertRaises(ValueError):
            get_tool_spec("write_arbitrary_sql")


if __name__ == "__main__":
    unittest.main()
