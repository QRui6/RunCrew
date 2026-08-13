from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.training_planning import (
    PlanAdjustmentRequest,
    TrainingPlanningResult,
    WeeklyPlanDraftRequest,
)


def main() -> None:
    output_dir = Path("skills/draft-running-plan/references")
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "draft-input.schema.json": WeeklyPlanDraftRequest.model_json_schema(),
        "adjust-input.schema.json": PlanAdjustmentRequest.model_json_schema(),
        "output.schema.json": TrainingPlanningResult.model_json_schema(),
    }
    for filename, schema in schemas.items():
        (output_dir / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
