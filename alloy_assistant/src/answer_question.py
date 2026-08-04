"""Run the full question-to-grounded-answer pipeline with Groq."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .answer_synthesis import GroundingError, synthesize_answer
from .database import DEFAULT_DATABASE_PATH, connect
from .evidence_bundle import build_evidence_bundle
from .groq_adapter import (
    DEFAULT_GROQ_MODEL,
    DEFAULT_MAX_OUTPUT_TOKENS,
    GroqAnswerModel,
    GroqConfigurationError,
    GroqResponseError,
)
from .hybrid_planner import plan_question_hybrid
from .route_question import plan_question
from .tool_executor import PlanExecutionError, execute_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Answer one question from reviewed SQL and PDF evidence.",
    )
    parser.add_argument("question")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Groq model ID. Defaults to GROQ_MODEL or "
            f"{DEFAULT_GROQ_MODEL}."
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
    )
    parser.add_argument(
        "--deterministic-router",
        action="store_true",
        help="Skip LLM evidence planning and use only the rule-based router.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    model = GroqAnswerModel(
        model=args.model,
        max_output_tokens=args.max_output_tokens,
    )
    plan = (
        plan_question(args.question)
        if args.deterministic_router
        else plan_question_hybrid(args.question, model)
    )
    with connect(database_path, read_only=True) as connection:
        tool_results = execute_plan(connection, plan)
    bundle = build_evidence_bundle(plan, tool_results)
    result = synthesize_answer(bundle, model)

    if args.json:
        print(
            json.dumps(
                {
                    "answer": result.answer,
                    "plan": asdict(plan),
                    "grounding": asdict(result.grounding),
                    "evidence": asdict(result.bundle),
                    "model": model.model,
                    "usage": (
                        None
                        if model.last_usage is None
                        else asdict(model.last_usage)
                    ),
                    "planning_usage": (
                        None
                        if model.last_planning_usage is None
                        else asdict(model.last_planning_usage)
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(result.answer)
        if model.last_planning_usage is not None:
            print(
                "\n---\n"
                f"Planner: {model.model} | "
                f"Tokens: {model.last_planning_usage.total_tokens} "
                f"({model.last_planning_usage.prompt_tokens} input, "
                f"{model.last_planning_usage.completion_tokens} output)"
            )
        if model.last_usage is not None:
            print(
                "\n"
                f"Model: {model.model} | "
                f"Tokens: {model.last_usage.total_tokens} "
                f"({model.last_usage.prompt_tokens} input, "
                f"{model.last_usage.completion_tokens} output)"
            )
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except (
        GroundingError,
        GroqConfigurationError,
        GroqResponseError,
        PlanExecutionError,
    ) as error:
        raise SystemExit(f"Error: {error}") from None
    raise SystemExit(exit_code)
