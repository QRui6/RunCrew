from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.runtime_evaluation import (
    RuntimeGovernanceEvaluationReport,
    RuntimeGovernanceEvaluationSuite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "schemas" / "runtime-evaluation"


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    exports = {
        "suite.schema.json": RuntimeGovernanceEvaluationSuite.model_json_schema(),
        "report.schema.json": RuntimeGovernanceEvaluationReport.model_json_schema(),
    }
    for name, schema in exports.items():
        (OUTPUT_DIRECTORY / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
