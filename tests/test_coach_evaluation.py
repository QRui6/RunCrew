from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.coach_evaluation import (
    CoachAgentEvaluationReport,
    CoachAgentEvaluationSuite,
)
from runcrew.evaluation import evaluate_coach_agent_suite, load_coach_agent_suite


CASES_PATH = Path("evals/coach_agent/cases.json")


def test_coach_suite_is_versioned_and_covers_required_categories() -> None:
    suite = load_coach_agent_suite(CASES_PATH)

    assert suite.suite_version == "coach-agent-eval/1.0"
    assert len(suite.cases) == 18
    assert len({case.id for case in suite.cases}) == 18
    assert {case.category for case in suite.cases} == {
        "task",
        "resilience",
        "guardrail",
        "budget",
        "approval",
    }


def test_coach_offline_baseline_passes_and_replays_with_same_hash() -> None:
    suite = load_coach_agent_suite(CASES_PATH)
    first = asyncio.run(evaluate_coach_agent_suite(suite))
    second = asyncio.run(evaluate_coach_agent_suite(suite))

    assert first.meets_baseline is True
    assert first.total_cases == 18
    assert first.passed_cases == 18
    assert first.failed_cases == 0
    assert first.suite_hash == second.suite_hash
    assert first.metrics.expectation_pass_rate == 1
    assert first.metrics.task_completion_rate == 1
    assert first.metrics.resilience_pass_rate == 1
    assert first.metrics.guardrail_pass_rate == 1
    assert first.metrics.approval_guard_pass_rate == 1
    assert first.metrics.schema_valid_rate == 1
    assert first.metrics.fact_integrity_rate == 1
    assert first.metrics.lineage_integrity_rate == 1
    assert first.metrics.confirmation_boundary_rate == 1
    assert first.metrics.prohibited_node_execution_count == 0


def test_coach_evaluation_detects_changed_expectation() -> None:
    suite = load_coach_agent_suite(CASES_PATH)
    changed = suite.cases[0].model_copy(update={"expected_status": "failed"})
    report = asyncio.run(
        evaluate_coach_agent_suite(
            suite.model_copy(update={"cases": [changed, *suite.cases[1:]]})
        )
    )

    assert report.meets_baseline is False
    assert report.failed_cases == 1
    assert "终态" in report.cases[0].failure_reasons[0]


def test_coach_evaluation_schemas_match_domain_models() -> None:
    directory = Path("evals/coach_agent")
    assert json.loads((directory / "cases.schema.json").read_text("utf-8")) == (
        CoachAgentEvaluationSuite.model_json_schema()
    )
    assert json.loads((directory / "report.schema.json").read_text("utf-8")) == (
        CoachAgentEvaluationReport.model_json_schema()
    )


def test_coach_evaluation_cli_writes_only_to_private_directory(tmp_path: Path) -> None:
    output_path = tmp_path / "coach-baseline.json"
    completed = CliRunner().invoke(
        app,
        ["eval", "coach-agent", "--output", str(output_path)],
    )

    assert completed.exit_code == 0, completed.output
    stdout_report = CoachAgentEvaluationReport.model_validate_json(completed.output)
    saved_report = CoachAgentEvaluationReport.model_validate_json(
        output_path.read_text("utf-8")
    )
    assert stdout_report.meets_baseline is True
    assert saved_report.suite_hash == stdout_report.suite_hash

    blocked_path = Path("evals/coach_agent/private-report.json")
    blocked = CliRunner().invoke(
        app,
        ["eval", "coach-agent", "--output", str(blocked_path)],
    )
    assert blocked.exit_code != 0
    assert not blocked_path.exists()
