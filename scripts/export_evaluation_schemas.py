from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.evaluation import (
    ReviewAgentEvaluationReport,
    ReviewAgentEvaluationSuite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "evals" / "review_agent"


def main() -> int:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    schemas = {
        "cases.schema.json": ReviewAgentEvaluationSuite.model_json_schema(),
        "report.schema.json": ReviewAgentEvaluationReport.model_json_schema(),
    }
    for filename, schema in schemas.items():
        (OUTPUT_DIRECTORY / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Exported {len(schemas)} schemas to {OUTPUT_DIRECTORY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
