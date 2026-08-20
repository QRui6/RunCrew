from __future__ import annotations

import json
from pathlib import Path

from runcrew.domain.demo import DemoSeedSummary


def main() -> None:
    target = Path("schemas/demo")
    target.mkdir(parents=True, exist_ok=True)
    target.joinpath("seed-output.schema.json").write_text(
        json.dumps(DemoSeedSummary.model_json_schema(), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

