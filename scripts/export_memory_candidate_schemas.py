from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.chat import ChatConversation, ChatTurnResult
from runcrew.domain.memory import (
    MemoryCandidate,
    MemoryCandidateDecisionRequest,
    MemoryCandidateDecisionResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "schemas" / "memory-candidate"


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    exports = {
        "candidate.schema.json": MemoryCandidate.model_json_schema(),
        "decision-input.schema.json": MemoryCandidateDecisionRequest.model_json_schema(),
        "decision-output.schema.json": MemoryCandidateDecisionResult.model_json_schema(),
        "chat-conversation.schema.json": ChatConversation.model_json_schema(),
        "chat-turn.schema.json": ChatTurnResult.model_json_schema(),
    }
    for name, schema in exports.items():
        OUTPUT_DIRECTORY.joinpath(name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
