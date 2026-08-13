from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.training_execution import (
    ExecutionConfirmationResult,
    TrainingExecutionDecisionRequest,
    TrainingExecutionRequest,
    TrainingExecutionResult,
)


def main() -> None:
    output_dir = Path("skills/compare-training-execution/references")
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "compare-input.schema.json": TrainingExecutionRequest.model_json_schema(),
        "decision-input.schema.json": TrainingExecutionDecisionRequest.model_json_schema(),
        "output.schema.json": TrainingExecutionResult.model_json_schema(),
        "decision-output.schema.json": ExecutionConfirmationResult.model_json_schema(),
    }
    for filename, schema in schemas.items():
        (output_dir / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
