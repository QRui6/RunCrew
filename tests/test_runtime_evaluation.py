from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.runtime_evaluation import (
    RuntimeGovernanceEvaluationReport,
    RuntimeGovernanceEvaluationSuite,
)
from runcrew.evaluation import (
    evaluate_runtime_governance_suite,
    load_runtime_governance_suite,
)


CASES_PATH = Path("evals/runtime_governance/cases.json")


def test_runtime_governance_suite_covers_five_fail_closed_boundaries() -> None:
    suite = load_runtime_governance_suite(CASES_PATH)
    report = evaluate_runtime_governance_suite(suite)

    assert report.meets_baseline
    assert report.passed_cases == report.total_cases == 5
    assert report.metrics.pre_execution_block_rate == 1
    assert report.metrics.invalid_output_block_rate == 1
    assert report.metrics.observability_failure_isolation_rate == 1
    assert report.metrics.prohibited_tool_execution_count == 0
    assert report.metrics.sensitive_error_leak_count == 0
    assert report.evidence_scope == "deterministic_synthetic_governance"
    serialized = report.model_dump_json()
    assert "private database failure" not in serialized


def test_runtime_governance_suite_hash_is_stable_and_versioned() -> None:
    suite = load_runtime_governance_suite(CASES_PATH)

    first = evaluate_runtime_governance_suite(suite)
    second = evaluate_runtime_governance_suite(suite)

    assert first.suite_version == "runtime-governance-eval/1.0"
    assert first.suite_hash == second.suite_hash


def test_runtime_governance_cli_is_offline_and_discoverable() -> None:
    completed = CliRunner().invoke(app, ["eval", "runtime-governance"])

    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["passed_cases"] == 5
    assert payload["meets_baseline"] is True


def test_runtime_evaluation_schemas_are_current() -> None:
    directory = Path("schemas/runtime-evaluation")

    assert json.loads((directory / "suite.schema.json").read_text("utf-8")) == (
        RuntimeGovernanceEvaluationSuite.model_json_schema()
    )
    assert json.loads((directory / "report.schema.json").read_text("utf-8")) == (
        RuntimeGovernanceEvaluationReport.model_json_schema()
    )
