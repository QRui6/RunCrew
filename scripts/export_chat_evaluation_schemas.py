from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.chat_evaluation import ChatEvaluationReport, ChatEvaluationSuite


def main() -> None:
    output_directory = Path("evals/running_chat")
    output_directory.mkdir(parents=True, exist_ok=True)
    schemas = {
        "cases.schema.json": ChatEvaluationSuite.model_json_schema(),
        "report.schema.json": ChatEvaluationReport.model_json_schema(),
    }
    for name, schema in schemas.items():
        (output_directory / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
