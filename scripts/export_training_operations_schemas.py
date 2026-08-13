from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.training_operations import (
    CheckInSubmission,
    CoachRunDecisionRequest,
    CoachRunDecisionResult,
    CoachRunSubmission,
    CoachRunView,
    TrainingOperationsBootstrap,
)


def main() -> None:
    target = Path("schemas/training-operations")
    target.mkdir(parents=True, exist_ok=True)
    schemas = {
        "bootstrap.schema.json": TrainingOperationsBootstrap.model_json_schema(),
        "check-in-input.schema.json": CheckInSubmission.model_json_schema(),
        "coach-run-input.schema.json": CoachRunSubmission.model_json_schema(),
        "coach-run-output.schema.json": CoachRunView.model_json_schema(),
        "decision-input.schema.json": CoachRunDecisionRequest.model_json_schema(),
        "decision-output.schema.json": CoachRunDecisionResult.model_json_schema(),
    }
    for name, schema in schemas.items():
        (target / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
