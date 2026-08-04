"""Offline tests for the bounded Groq answer adapter."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from alloy_assistant.src.groq_adapter import (
    GroqAnswerModel,
    GroqConfigurationError,
    GroqResponseError,
)


class FakeCompletions:
    def __init__(
        self,
        content: str | None = (
            '{"direct_answer":{"text":"Answer","evidence_ids":["S1"]},'
            '"supporting_points":[],"limitations":[]}'
        ),
    ) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
            ),
        )


class FakeClient:
    def __init__(
        self,
        content: str | None = (
            '{"direct_answer":{"text":"Answer","evidence_ids":["S1"]},'
            '"supporting_points":[],"limitations":[]}'
        ),
    ) -> None:
        self.completions = FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


class FailingCompletions:
    def create(self, **kwargs: object) -> SimpleNamespace:
        raise ValueError("provider rejected request")


class GroqAdapterTest(unittest.TestCase):
    def test_missing_api_key_is_explicit(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                GroqConfigurationError,
                "GROQ_API_KEY",
            ):
                GroqAnswerModel()

    def test_request_is_bounded_and_usage_is_recorded(self) -> None:
        client = FakeClient()
        model = GroqAnswerModel(
            client=client,
            model="test-model",
            max_output_tokens=500,
        )
        answer = model.generate(
            "system",
            "user",
            evidence_ids=("S1", "D1"),
        )
        call = client.completions.calls[0]
        self.assertEqual(answer, "Answer [S1]")
        self.assertEqual(call["model"], "test-model")
        self.assertEqual(call["max_completion_tokens"], 500)
        self.assertEqual(call["temperature"], 0.1)
        self.assertEqual(call["reasoning_effort"], "low")
        response_format = call["response_format"]
        self.assertTrue(response_format["json_schema"]["strict"])
        evidence_schema = response_format["json_schema"]["schema"][
            "properties"
        ]["direct_answer"]["properties"]["evidence_ids"]
        self.assertEqual(
            evidence_schema["items"]["enum"],
            ["S1", "D1", "NONE"],
        )
        self.assertEqual(evidence_schema["maxItems"], 3)
        self.assertEqual(model.last_usage.total_tokens, 120)

    def test_one_point_can_render_structured_and_document_citations(self) -> None:
        content = (
            '{"direct_answer":{"text":"Assessment",'
            '"evidence_ids":["S1","D1"]},'
            '"supporting_points":[],"limitations":[]}'
        )
        model = GroqAnswerModel(client=FakeClient(content=content))
        answer = model.generate(
            "system",
            "user",
            evidence_ids=("S1", "D1"),
        )
        self.assertEqual(answer, "Assessment [S1] [D1]")

    def test_duplicate_point_citations_are_rejected_locally(self) -> None:
        content = (
            '{"direct_answer":{"text":"Assessment",'
            '"evidence_ids":["S1","S1"]},'
            '"supporting_points":[],"limitations":[]}'
        )
        model = GroqAnswerModel(client=FakeClient(content=content))
        with self.assertRaisesRegex(GroqResponseError, "duplicate"):
            model.generate("system", "user", evidence_ids=("S1",))

    def test_schema_allows_evidence_complete_candidate_point(self) -> None:
        evidence_ids = tuple(f"S{index}" for index in range(1, 12))
        schema = GroqAnswerModel._response_format(evidence_ids)
        evidence_schema = schema["json_schema"]["schema"]["properties"][
            "direct_answer"
        ]["properties"]["evidence_ids"]
        self.assertEqual(evidence_schema["maxItems"], 12)

    def test_local_input_cap_prevents_api_call(self) -> None:
        client = FakeClient()
        model = GroqAnswerModel(
            client=client,
            max_input_characters=1_000,
        )
        with self.assertRaisesRegex(GroqConfigurationError, "input cap"):
            model.generate("x" * 600, "y" * 600)
        self.assertEqual(client.completions.calls, [])

    def test_structured_planning_request_is_bounded(self) -> None:
        content = (
            '{"tool_calls":[{"tool_name":"get_pmr_for_system",'
            '"arguments_json":"{\\\\\\"system_name\\\\\\":'
            '\\\\\\"Mo-Nb-Ta-W\\\\\\"}",'
            '"reason":"Retrieve PMR."}],"coverage_notes":[]}'
        )
        client = FakeClient(content=content)
        model = GroqAnswerModel(
            client=client,
            model="test-model",
            max_output_tokens=1_200,
        )
        payload = model.plan_tools(
            "system",
            "user",
            tool_names=("get_pmr_for_system", "hybrid_search"),
        )
        call = client.completions.calls[0]
        self.assertEqual(
            payload["tool_calls"][0]["tool_name"],
            "get_pmr_for_system",
        )
        self.assertEqual(call["temperature"], 0.0)
        self.assertEqual(call["max_completion_tokens"], 900)
        tool_schema = call["response_format"]["json_schema"]["schema"][
            "properties"
        ]["tool_calls"]["items"]["properties"]["tool_name"]
        self.assertEqual(
            tool_schema["enum"],
            ["get_pmr_for_system", "hybrid_search"],
        )
        self.assertEqual(model.last_planning_usage.total_tokens, 120)

    def test_empty_provider_response_is_rejected(self) -> None:
        model = GroqAnswerModel(client=FakeClient(content=None))
        with self.assertRaisesRegex(GroqResponseError, "empty answer"):
            model.generate("system", "user")

    def test_provider_error_is_wrapped_for_the_cli(self) -> None:
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=FailingCompletions())
        )
        model = GroqAnswerModel(client=client)
        with self.assertRaisesRegex(
            GroqResponseError,
            "provider rejected request",
        ):
            model.generate("system", "user")


if __name__ == "__main__":
    unittest.main()
