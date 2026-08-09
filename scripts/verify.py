from __future__ import annotations

import compileall
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "pyproject.toml",
    "scripts/export_evaluation_schemas.py",
    "docs/PROJECT_CONTEXT.md",
    "docs/RunCrew-项目实施全景与面试说明.md",
    "docs/M5-B-DeepSeek模型选型与接入方案.md",
    "docs/CURRENT_STATE.md",
    "docs/ARCHITECTURE.md",
    "docs/ROADMAP.md",
    "docs/PROGRESS.md",
    "docs/IMPLEMENTATION_STATUS.md",
    "docs/adr/0008-versioned-offline-agent-evaluation.md",
    "docs/adr/0009-deepseek-policy-adapter-boundary.md",
    "docs/progress/2026-08-09-m3-training-review-skill.md",
    "docs/progress/2026-08-09-m4-review-agent-loop.md",
    "docs/progress/2026-08-09-m5-agent-evaluation-baseline.md",
    "docs/progress/2026-08-09-m5b-deepseek-policy-adapter.md",
    "evals/review_agent/cases.json",
    "evals/review_agent/cases.schema.json",
    "evals/review_agent/report.schema.json",
    "src/runcrew/policies/deepseek.py",
    "skills/review-running-training/SKILL.md",
    "skills/review-running-training/agents/openai.yaml",
    "skills/review-running-training/references/input.schema.json",
    "skills/review-running-training/references/output.schema.json",
    "skills/review-running-training/references/agent-run-input.schema.json",
    "skills/review-running-training/references/agent-run-output.schema.json",
]


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not (PROJECT_ROOT / path).exists()]
    if missing:
        print("Missing required project files:")
        for path in missing:
            print(f"- {path}")
        return 1

    if not compileall.compile_dir(PROJECT_ROOT / "src", quiet=1):
        print("Python compilation failed.")
        return 1

    completed = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if completed.returncode:
        return completed.returncode

    print("Project verification passed: required docs, compilation, and tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
