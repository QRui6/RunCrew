from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

import runcrew.cli as cli_module
from runcrew.cli import app
from runcrew.domain.chat import ChatAnswer, ChatTurnUsage
from runcrew.domain.chat_evaluation import ChatEvaluationReport, ChatEvaluationSuite
from runcrew.evaluation.chat import evaluate_chat_suite, load_chat_evaluation_suite


CASES_PATH = Path("evals/running_chat/cases.json")


def test_chat_suite_is_versioned_and_covers_grounding_openness_safety_context() -> None:
    suite = load_chat_evaluation_suite(CASES_PATH)

    assert suite.suite_version == "running-chat-eval/1.0"
    assert len(suite.cases) == 7
    assert sum(len(case.turns) for case in suite.cases) == 8
    assert {case.category for case in suite.cases} == {
        "grounding",
        "openness",
        "safety",
        "context",
    }


def test_offline_flexible_chat_baseline_passes_and_is_replayable() -> None:
    suite = load_chat_evaluation_suite(CASES_PATH)
    first = asyncio.run(evaluate_chat_suite(suite))
    second = asyncio.run(evaluate_chat_suite(suite))

    assert first.meets_baseline is True
    assert first.passed_turns == first.total_turns == 8
    assert first.suite_hash == second.suite_hash
    assert first.metrics.turn_pass_rate == 1
    assert first.metrics.grounding_pass_rate == 1
    assert first.metrics.openness_pass_rate == 1
    assert first.metrics.safety_pass_rate == 1
    assert first.metrics.total_tokens == 0


class _OverGroundedPolicy:
    async def answer(self, *, question, activity_context, review, history):
        del question, activity_context, review, history
        return (
            ChatAnswer(
                answer="把所有问题都错误地说成你的个人数据结论。",
                response_mode="data_analysis",
                evidence_refs=["training_anomaly"],
                confidence="high",
            ),
            ChatTurnUsage(provider="offline", model="bad-test-policy"),
        )


def test_chat_evaluation_rejects_rigid_over_grounding() -> None:
    source = load_chat_evaluation_suite(CASES_PATH)
    general_case = next(case for case in source.cases if case.id == "open_general_knowledge")
    suite = source.model_copy(update={"cases": [general_case]})

    report = asyncio.run(
        evaluate_chat_suite(
            suite,
            policy_factory=_OverGroundedPolicy,
            policy_name="over-grounded-test",
        )
    )

    assert report.meets_baseline is False
    assert report.passed_turns == 0
    assert any("模式" in reason for reason in report.turns[0].failure_reasons)
    assert any("个人数据事实" in reason for reason in report.turns[0].failure_reasons)


def test_exported_chat_evaluation_schemas_match_models() -> None:
    directory = Path("evals/running_chat")
    assert json.loads((directory / "cases.schema.json").read_text("utf-8")) == (
        ChatEvaluationSuite.model_json_schema()
    )
    assert json.loads((directory / "report.schema.json").read_text("utf-8")) == (
        ChatEvaluationReport.model_json_schema()
    )


def test_chat_evaluation_cli_and_paid_safety_gate(monkeypatch) -> None:
    offline = CliRunner().invoke(app, ["eval", "running-chat"])
    assert offline.exit_code == 0, offline.output
    assert ChatEvaluationReport.model_validate_json(offline.output).meets_baseline

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    missing_confirmation = CliRunner().invoke(app, ["eval", "deepseek-chat-suite"])
    assert missing_confirmation.exit_code != 0
    assert "--confirm-paid-api" in missing_confirmation.output

    missing_cap = CliRunner().invoke(
        app,
        ["eval", "deepseek-chat-suite", "--confirm-paid-api"],
    )
    assert missing_cap.exit_code != 0
    assert "--max-total-estimated-cost-usd" in missing_cap.output

    blocked_output = Path("evals/running_chat/private-report.json")
    blocked = CliRunner().invoke(
        app,
        ["eval", "running-chat", "--output", str(blocked_output)],
    )
    assert blocked.exit_code != 0
    assert not blocked_output.exists()


def test_deepseek_chat_cli_preserves_suite_and_shared_budget(monkeypatch) -> None:
    source_suite = load_chat_evaluation_suite(CASES_PATH)
    captured = {}

    class SuccessfulReport:
        meets_baseline = True

        @staticmethod
        def model_dump_json(*, indent: int) -> str:
            assert indent == 2
            return '{"meets_baseline":true}'

    async def fake_evaluate(suite, **kwargs):
        captured["suite"] = suite
        captured["policy_name"] = kwargs["policy_name"]
        captured["policy_factory"] = kwargs["policy_factory"]
        return SuccessfulReport()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-local-test-only")
    monkeypatch.setattr(cli_module, "evaluate_chat_suite", fake_evaluate)

    completed = CliRunner().invoke(
        app,
        [
            "eval",
            "deepseek-chat-suite",
            "--confirm-paid-api",
            "--max-total-estimated-cost-usd",
            "0.01",
        ],
    )

    assert completed.exit_code == 0, completed.output
    assert captured["suite"].model_dump(mode="json") == source_suite.model_dump(
        mode="json"
    )
    assert captured["policy_name"] == "deepseek-v4-flash-live-flexible-chat-suite"
    assert captured["policy_factory"] is not None
