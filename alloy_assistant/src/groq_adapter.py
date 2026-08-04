"""Groq implementation of the provider-independent answer model interface."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_MAX_OUTPUT_TOKENS = 1_200
DEFAULT_MAX_INPUT_CHARACTERS = 24_000


class GroqConfigurationError(RuntimeError):
    """Raised when Groq credentials or adapter settings are incomplete."""


class GroqResponseError(RuntimeError):
    """Raised when Groq returns no usable answer text."""


@dataclass(frozen=True)
class GroqUsage:
    """Token counts reported by Groq for the most recent request."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GroqAnswerModel:
    """Generate one bounded answer through Groq Chat Completions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        max_input_characters: int = DEFAULT_MAX_INPUT_CHARACTERS,
        client: Any | None = None,
    ) -> None:
        if max_output_tokens < 1 or max_output_tokens > 2_000:
            raise ValueError("max_output_tokens must be between 1 and 2000")
        if max_input_characters < 1_000:
            raise ValueError("max_input_characters must be at least 1000")

        configured_model = (
            model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        ).strip()
        if not configured_model:
            raise GroqConfigurationError("The Groq model name is empty.")

        if client is None:
            configured_key = api_key or os.environ.get("GROQ_API_KEY")
            if not configured_key or not configured_key.strip():
                raise GroqConfigurationError(
                    "GROQ_API_KEY is not configured. Create a Groq API key "
                    "and export it in your shell; never commit it to the repo."
                )
            try:
                from groq import Groq
            except ImportError as error:
                raise GroqConfigurationError(
                    "The groq package is not installed. Run "
                    "`python -m pip install -r requirements.txt`."
                ) from error
            client = Groq(api_key=configured_key.strip())

        self.client = client
        self.model = configured_model
        self.max_output_tokens = max_output_tokens
        self.max_input_characters = max_input_characters
        self.last_usage: GroqUsage | None = None
        self.last_planning_usage: GroqUsage | None = None

    @staticmethod
    def _response_format(
        evidence_ids: tuple[str, ...],
    ) -> dict[str, object]:
        allowed_ids = [*evidence_ids, "NONE"]
        max_citations_per_point = min(20, len(allowed_ids))
        supported_point = {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "evidence_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": allowed_ids,
                    },
                    "minItems": 1,
                    "maxItems": max_citations_per_point,
                },
            },
            "required": ["text", "evidence_ids"],
            "additionalProperties": False,
        }
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "grounded_alloy_answer",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "direct_answer": supported_point,
                        "supporting_points": {
                            "type": "array",
                            "items": supported_point,
                        },
                        "limitations": {
                            "type": "array",
                            "items": supported_point,
                        },
                    },
                    "required": [
                        "direct_answer",
                        "supporting_points",
                        "limitations",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _render_answer(payload: dict[str, object]) -> str:
        def render_point(value: object) -> str:
            if not isinstance(value, dict):
                raise GroqResponseError(
                    "Groq returned an invalid answer point."
                )
            text = str(value.get("text", "")).strip()
            evidence_value = value.get("evidence_ids")
            if not text or not isinstance(evidence_value, list):
                raise GroqResponseError(
                    "Groq returned an incomplete answer point."
                )
            evidence_ids = [
                str(evidence_id).strip()
                for evidence_id in evidence_value
                if str(evidence_id).strip()
            ]
            if not evidence_ids or len(evidence_ids) != len(evidence_value):
                raise GroqResponseError(
                    "Groq returned an incomplete answer point."
                )
            if len(set(evidence_ids)) != len(evidence_ids):
                raise GroqResponseError(
                    "Groq returned duplicate evidence IDs in one point."
                )
            if "NONE" in evidence_ids and len(evidence_ids) > 1:
                raise GroqResponseError(
                    "NONE cannot be combined with evidence IDs."
                )
            suffix = "".join(
                f" [{evidence_id}]"
                for evidence_id in evidence_ids
                if evidence_id != "NONE"
            )
            return f"{text}{suffix}"

        def render_points(value: object) -> list[str]:
            if not isinstance(value, list):
                raise GroqResponseError(
                    "Groq returned an invalid structured answer."
                )
            return [render_point(point) for point in value]

        direct_answer = render_point(payload.get("direct_answer"))
        supporting_points = render_points(payload.get("supporting_points"))
        limitations = render_points(payload.get("limitations"))
        answer = "\n\n".join([direct_answer, *supporting_points])
        if limitations:
            answer += "\n\n### Limitations\n\n" + "\n\n".join(limitations)
        return answer

    @staticmethod
    def _planning_response_format(
        tool_names: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "alloy_evidence_plan",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "tool_calls": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tool_name": {
                                        "type": "string",
                                        "enum": list(tool_names),
                                    },
                                    "arguments_json": {"type": "string"},
                                    "reason": {"type": "string"},
                                },
                                "required": [
                                    "tool_name",
                                    "arguments_json",
                                    "reason",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "coverage_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["tool_calls", "coverage_notes"],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _usage(completion: object) -> GroqUsage | None:
        usage = getattr(completion, "usage", None)
        if usage is None:
            return None
        return GroqUsage(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0)),
            completion_tokens=int(getattr(usage, "completion_tokens", 0)),
            total_tokens=int(getattr(usage, "total_tokens", 0)),
        )

    def plan_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        tool_names: tuple[str, ...],
    ) -> dict[str, object]:
        """Return a bounded structured evidence plan for reviewed tools."""
        if not tool_names:
            raise ValueError("tool_names must not be empty")
        input_characters = len(system_prompt) + len(user_prompt)
        if input_characters > self.max_input_characters:
            raise GroqConfigurationError(
                "Planning prompt exceeds the local Groq input cap: "
                f"{input_characters} > {self.max_input_characters} characters."
            )
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_completion_tokens=min(900, self.max_output_tokens),
                reasoning_effort="low",
                response_format=self._planning_response_format(tool_names),
            )
        except Exception as error:
            raise GroqResponseError(
                "Groq planning request failed with "
                f"{type(error).__name__}: {error}"
            ) from error
        content = completion.choices[0].message.content
        if not content or not str(content).strip():
            raise GroqResponseError("Groq returned an empty evidence plan.")
        self.last_planning_usage = self._usage(completion)
        try:
            payload = json.loads(str(content))
        except json.JSONDecodeError as error:
            raise GroqResponseError(
                "Groq returned invalid JSON for the evidence plan."
            ) from error
        if not isinstance(payload, dict):
            raise GroqResponseError("Groq returned a non-object evidence plan.")
        return payload

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        evidence_ids: tuple[str, ...] = (),
    ) -> str:
        """Send one strict synthesis request without tools or retries."""
        input_characters = len(system_prompt) + len(user_prompt)
        if input_characters > self.max_input_characters:
            raise GroqConfigurationError(
                "Synthesis prompt exceeds the local Groq input cap: "
                f"{input_characters} > {self.max_input_characters} characters."
            )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            system_prompt
                            + "\nReturn an atomic direct answer and optional "
                            "supporting points. Put every record needed to "
                            "support a point in its evidence_ids field. "
                            "A named-alloy interpretation "
                            "that applies general document context to "
                            "structured facts must include both an S# and "
                            "the relevant D#. "
                            "Leave supporting_points empty when they would "
                            "merely repeat the direct answer. "
                            "Use NONE by itself only for a packet-level "
                            "limitation or "
                            "explicitly labeled inference that no supplied "
                            "record directly supports; Python will render the "
                            "visible citations."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_completion_tokens=self.max_output_tokens,
                reasoning_effort="low",
                response_format=self._response_format(evidence_ids),
            )
        except Exception as error:
            raise GroqResponseError(
                "Groq request failed with "
                f"{type(error).__name__}: {error}"
            ) from error
        content = completion.choices[0].message.content
        if not content or not str(content).strip():
            raise GroqResponseError("Groq returned an empty answer.")

        self.last_usage = self._usage(completion)
        try:
            payload = json.loads(str(content))
        except json.JSONDecodeError as error:
            raise GroqResponseError(
                "Groq returned invalid JSON despite structured-output mode."
            ) from error
        if not isinstance(payload, dict):
            raise GroqResponseError("Groq returned a non-object answer.")
        return self._render_answer(payload)
