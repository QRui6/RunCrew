from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.memory_evaluation import (
    MemoryEvaluationReport,
    MemoryEvaluationSuite,
)
from runcrew.evaluation import evaluate_memory_suite, load_memory_evaluation_suite


CASES_PATH = Path("evals/memory/cases.json")
EXPECTED_SUITE_HASH = (
    "78e9e4dc7c1e75cb94fbbbfbc60cb9b9b74874da7555757a58487567892d51ef"
)


def test_memory_suite_is_versioned_and_covers_required_categories() -> None:
    suite = load_memory_evaluation_suite(CASES_PATH)

    assert suite.suite_version == "memory-manager-eval/1.0"
    assert len(suite.cases) == 16
    assert len({case.id for case in suite.cases}) == 16
    assert {case.category for case in suite.cases} == {
        "candidate",
        "lifecycle",
        "integrity",
        "retrieval",
    }


def test_memory_baseline_passes_with_frozen_hash_and_metrics() -> None:
    report = evaluate_memory_suite(load_memory_evaluation_suite(CASES_PATH))

    assert report.meets_baseline is True
    assert report.total_cases == 16
    assert report.passed_cases == 16
    assert report.failed_cases == 0
    assert report.suite_hash == EXPECTED_SUITE_HASH
    assert report.metrics.expectation_pass_rate == 1
    assert report.metrics.candidate_recall_rate == 1
    assert report.metrics.negative_rejection_rate == 1
    assert report.metrics.lifecycle_integrity_rate == 1
    assert report.metrics.source_integrity_rate == 1
    assert report.metrics.confirmation_boundary_rate == 1
    assert report.metrics.role_scope_rate == 1
    assert report.metrics.irrelevant_injection_resistance_rate == 1
    assert report.metrics.schema_valid_rate == 1
    assert report.metrics.unexpected_formal_memory_write_count == 0


def test_memory_evaluation_detects_changed_expectation() -> None:
    suite = load_memory_evaluation_suite(CASES_PATH)
    first = suite.cases[0]
    changed = first.model_copy(
        update={
            "expected": first.expected.model_copy(
                update={"candidate_created": False}
            )
        }
    )
    report = evaluate_memory_suite(
        suite.model_copy(update={"cases": [changed, *suite.cases[1:]]})
    )

    assert report.meets_baseline is False
    assert report.failed_cases == 1
    assert "版本化期望" in report.cases[0].failure_reasons[0]


def test_memory_evaluation_schemas_match_domain_models() -> None:
    directory = Path("evals/memory")
    assert json.loads((directory / "cases.schema.json").read_text("utf-8")) == (
        MemoryEvaluationSuite.model_json_schema()
    )
    assert json.loads((directory / "report.schema.json").read_text("utf-8")) == (
        MemoryEvaluationReport.model_json_schema()
    )


def test_memory_evaluation_cli_writes_only_to_private_directory(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "memory-baseline.json"
    completed = CliRunner().invoke(
        app,
        ["eval", "memory", "--output", str(output_path)],
    )

    assert completed.exit_code == 0, completed.output
    stdout_report = MemoryEvaluationReport.model_validate_json(completed.output)
    saved_report = MemoryEvaluationReport.model_validate_json(
        output_path.read_text("utf-8")
    )
    assert stdout_report.meets_baseline is True
    assert saved_report.suite_hash == EXPECTED_SUITE_HASH

    blocked_path = Path("evals/memory/private-report.json")
    blocked = CliRunner().invoke(
        app,
        ["eval", "memory", "--output", str(blocked_path)],
    )
    assert blocked.exit_code != 0
    assert not blocked_path.exists()
