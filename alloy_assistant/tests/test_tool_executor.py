"""Tests for strict execution of reviewed question plans."""

from __future__ import annotations

import unittest

from alloy_assistant.src.database import connect, initialize_schema
from alloy_assistant.src.route_question import plan_question
from alloy_assistant.src.tool_executor import (
    PlanExecutionError,
    execute_plan,
)


class ToolExecutorTest(unittest.TestCase):
    """Ensure incomplete and unsupported plans cannot execute."""

    def setUp(self) -> None:
        self.manager = connect(":memory:")
        self.connection = self.manager.__enter__()
        initialize_schema(self.connection)

    def tearDown(self) -> None:
        self.manager.__exit__(None, None, None)

    def test_reviewed_sql_tool_executes(self) -> None:
        plan = plan_question("Give me the database summary.")
        results = execute_plan(self.connection, plan)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_name, "get_database_summary")
        self.assertEqual(results[0].value.sources, 0)

    def test_missing_required_argument_stops_execution(self) -> None:
        plan = plan_question("What is the miscibility temperature?")
        with self.assertRaisesRegex(
            PlanExecutionError,
            "system_name",
        ):
            execute_plan(self.connection, plan)

    def test_known_coverage_gap_stops_execution(self) -> None:
        plan = plan_question("Which system has the highest PMR at 1000 K?")
        with self.assertRaisesRegex(
            PlanExecutionError,
            "not covered",
        ):
            execute_plan(self.connection, plan)


if __name__ == "__main__":
    unittest.main()
