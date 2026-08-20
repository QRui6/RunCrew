from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.runtime_governance import (
    ToolInvocationGuardrailResult,
    ToolManifest,
    ToolOutputGuardrailResult,
)
from runcrew.services.runtime_governance import build_default_tool_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "schemas" / "runtime-governance"


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    exports = {
        "tool-manifest.schema.json": ToolManifest.model_json_schema(),
        "invocation-result.schema.json": ToolInvocationGuardrailResult.model_json_schema(),
        "output-result.schema.json": ToolOutputGuardrailResult.model_json_schema(),
        "default-tool-registry.json": [
            item.model_dump(mode="json")
            for item in build_default_tool_registry().list()
        ],
    }
    for name, payload in exports.items():
        (OUTPUT_DIRECTORY / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
