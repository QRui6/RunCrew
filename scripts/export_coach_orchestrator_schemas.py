from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult


def main() -> None:
    target = Path("schemas/coach-orchestrator")
    target.mkdir(parents=True, exist_ok=True)
    schemas = {
        "input.schema.json": CoachAgentRunRequest.model_json_schema(),
        "output.schema.json": CoachAgentRunResult.model_json_schema(),
    }
    for name, schema in schemas.items():
        (target / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
