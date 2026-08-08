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
    "docs/PROJECT_CONTEXT.md",
    "docs/CURRENT_STATE.md",
    "docs/ARCHITECTURE.md",
    "docs/ROADMAP.md",
    "docs/PROGRESS.md",
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

