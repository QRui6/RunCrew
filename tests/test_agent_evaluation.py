from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.evaluation import (
    ReviewAgentEvaluationReport,
    ReviewAgentEvaluationSuite,
)
from runcrew.evaluation import evaluate_review_agent_suite, load_review_agent_suite


CASES_PATH = Path("evals/review_agent/cases.json")


def test_evaluation_suite_is_versioned_and_contains_unique_scenarios() -> None:
    suite = load_review_agent_suite(CASES_PATH)

    assert suite.suite_version == "review-agent-eval/1.0"
    assert len(suite.cases) == 12
    assert len({case.id for case in suite.cases}) == 12
    assert {case.category for case in suite.cases} == {
        "task",
        "resilience",
        "guardrail",
        "budget",
    }


def test_offline_baseline_passes_all_metrics_and_is_replayable() -> None:
    suite = load_review_agent_suite(CASES_PATH)
    first = asyncio.run(evaluate_review_agent_suite(suite))
    second = asyncio.run(evaluate_review_agent_suite(suite))

    assert first.meets_baseline is True
    assert first.total_cases == 12
    assert first.passed_cases == 12
    assert first.failed_cases == 0
    assert first.suite_hash == second.suite_hash
    assert first.metrics.expectation_pass_rate == 1
    assert first.metrics.task_completion_rate == 1
    assert first.metrics.guardrail_pass_rate == 1
    assert first.metrics.schema_valid_rate == 1
    assert first.metrics.fact_integrity_rate == 1
    assert first.metrics.prohibited_tool_execution_count == 0
    assert first.metrics.average_tool_calls <= 1
    assert first.metrics.termination_reason_counts["completed"] == 3
    assert all(case.passed for case in first.cases)


def test_evaluation_detects_a_changed_expectation() -> None:
    suite = load_review_agent_suite(CASES_PATH)
    changed_case = suite.cases[0].model_copy(
        update={"expected_finding_levels": ["attention", "attention", "attention"]}
    )
    changed_suite = suite.model_copy(
        update={"cases": [changed_case, *suite.cases[1:]]}
    )

    report = asyncio.run(evaluate_review_agent_suite(changed_suite))

    assert report.meets_baseline is False
    assert report.failed_cases == 1
    assert report.cases[0].passed is False
    assert "finding 等级" in report.cases[0].failure_reasons[0]


def test_exported_evaluation_schemas_match_domain_models() -> None:
    directory = Path("evals/review_agent")
    assert json.loads((directory / "cases.schema.json").read_text("utf-8")) == (
        ReviewAgentEvaluationSuite.model_json_schema()
    )
    assert json.loads((directory / "report.schema.json").read_text("utf-8")) == (
        ReviewAgentEvaluationReport.model_json_schema()
    )


def test_evaluation_cli_writes_valid_report_only_to_private_directory(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "baseline.json"
    completed = CliRunner().invoke(
        app,
        [
            "eval",
            "review-agent",
            "--cases",
            str(CASES_PATH),
            "--output",
            str(output_path),
        ],
    )

    assert completed.exit_code == 0, completed.output
    stdout_report = ReviewAgentEvaluationReport.model_validate_json(completed.output)
    saved_report = ReviewAgentEvaluationReport.model_validate_json(
        output_path.read_text("utf-8")
    )
    assert stdout_report.meets_baseline is True
    assert saved_report.suite_hash == stdout_report.suite_hash

    blocked_path = Path("evals/review_agent/private-report.json")
    blocked = CliRunner().invoke(
        app,
        [
            "eval",
            "review-agent",
            "--output",
            str(blocked_path),
        ],
    )
    assert blocked.exit_code != 0
    assert not blocked_path.exists()
