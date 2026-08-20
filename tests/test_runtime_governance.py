from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from runcrew.domain.agent import REVIEW_TOOL_NAME
from runcrew.domain.runtime_governance import (
    ToolInvocationGuardrailResult,
    ToolManifest,
    ToolOutputGuardrailResult,
)
from runcrew.domain.training_execution import TrainingExecutionResult
from runcrew.domain.training_review import TrainingReviewRequest, TrainingReviewResult
from runcrew.services.runtime_governance import (
    RuntimeGuardrailEngine,
    ToolCapabilityRegistry,
    build_default_tool_registry,
    guardrail_trace_details,
)


def review_request(identifier: str = "activity-1") -> TrainingReviewRequest:
    return TrainingReviewRequest(target_activity_id=identifier)


def evaluate_review(**overrides):
    values = {
        "tool_name": REVIEW_TOOL_NAME,
        "owner_role": "review_agent",
        "granted_access": "read",
        "actual_arguments": review_request(),
        "expected_arguments": review_request(),
        "timeout_seconds": 5,
        "max_retries": 1,
    }
    values.update(overrides)
    return RuntimeGuardrailEngine().evaluate_invocation(**values)


def test_default_registry_contains_only_four_real_agent_tools() -> None:
    manifests = build_default_tool_registry().list()

    assert [item.tool_name for item in manifests] == [
        "adjust_running_plan",
        "assess_running_recovery",
        "compare_training_execution",
        "review_running_training",
    ]
    assert all(not item.can_persist and not item.can_approve for item in manifests)
    assert next(
        item for item in manifests if item.tool_name == "adjust_running_plan"
    ).side_effect == "state_proposal"


def test_registry_rejects_duplicate_tool_name() -> None:
    manifest = build_default_tool_registry().get(REVIEW_TOOL_NAME)
    assert manifest is not None

    with pytest.raises(ValueError, match="重复注册"):
        ToolCapabilityRegistry([manifest, manifest])


def test_manifest_rejects_unconfirmed_critical_mutation() -> None:
    with pytest.raises(ValidationError, match="人工确认"):
        ToolManifest(
            tool_name="commit_plan",
            owner_role="plan_agent",
            description="测试写入工具。",
            input_schema="Input",
            output_schema="Output",
            access_level="commit_change",
            side_effect="state_mutation",
            risk_level="critical",
            can_persist=True,
            idempotent=False,
            maximum_timeout_seconds=5,
            maximum_retries=0,
        )


def test_unknown_tool_role_access_and_capability_escalation_fail_closed() -> None:
    unknown = evaluate_review(tool_name="delete_activity")
    wrong_role = evaluate_review(owner_role="recovery_agent")
    wrong_access = evaluate_review(granted_access="prepare_change")
    escalated = evaluate_review(can_persist=True)

    assert not unknown.allowed
    assert unknown.decisions[0].rule_id == "tool.registered/1.0"
    assert any(item.rule_id == "tool.owner-role/1.0" and item.outcome == "deny" for item in wrong_role.decisions)
    assert any(item.rule_id == "tool.access-level/1.0" and item.outcome == "deny" for item in wrong_access.decisions)
    assert any(item.rule_id == "tool.capability-ceiling/1.0" and item.outcome == "deny" for item in escalated.decisions)


def test_argument_tampering_confirmation_and_runtime_overrun_block_before_execution() -> None:
    tampered = evaluate_review(actual_arguments=review_request("changed"))
    confirmation = evaluate_review(confirmation_required=True, confirmed=False)
    overrun = evaluate_review(timeout_seconds=61, max_retries=4)

    assert not tampered.allowed
    assert tampered.input_hash != tampered.expected_input_hash
    assert any(item.rule_id == "tool.argument-integrity/1.0" and item.outcome == "deny" for item in tampered.decisions)
    assert not confirmation.allowed
    assert any(item.outcome == "require_confirmation" for item in confirmation.decisions)
    assert not overrun.allowed
    assert any(item.rule_id == "tool.runtime-limits/1.0" and item.outcome == "deny" for item in overrun.decisions)


def test_trace_summary_contains_hashes_and_rules_but_not_raw_arguments() -> None:
    result = evaluate_review()
    trace = guardrail_trace_details(result)
    serialized = json.dumps(trace, ensure_ascii=False)

    assert result.allowed
    assert trace["input_hash_match"] is True
    assert len(trace["manifest_hash"]) == 64
    assert "activity-1" not in serialized
    assert "tool.argument-integrity/1.0" in serialized


def test_output_guardrail_rejects_manifest_mismatched_schema() -> None:
    engine = RuntimeGuardrailEngine()
    output, result = engine.validate_output(
        tool_name=REVIEW_TOOL_NAME,
        raw_output={},
        output_model=TrainingExecutionResult,
    )

    assert output is None
    assert not result.allowed
    assert result.decision.rule_id == "tool.output-schema/1.0"
    invalid_output, invalid_result = engine.validate_output(
        tool_name=REVIEW_TOOL_NAME,
        raw_output={},
        output_model=TrainingReviewResult,
    )
    assert invalid_output is None
    assert invalid_result.decision.details["validation_error_count"] > 0


def test_exported_runtime_governance_artifacts_match_models() -> None:
    schema_dir = Path("schemas/runtime-governance")

    assert json.loads((schema_dir / "tool-manifest.schema.json").read_text("utf-8")) == ToolManifest.model_json_schema()
    assert json.loads((schema_dir / "invocation-result.schema.json").read_text("utf-8")) == ToolInvocationGuardrailResult.model_json_schema()
    assert json.loads((schema_dir / "output-result.schema.json").read_text("utf-8")) == ToolOutputGuardrailResult.model_json_schema()
    assert json.loads((schema_dir / "default-tool-registry.json").read_text("utf-8")) == [
        item.model_dump(mode="json") for item in build_default_tool_registry().list()
    ]
