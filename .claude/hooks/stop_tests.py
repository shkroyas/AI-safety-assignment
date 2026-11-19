#!/usr/bin/env python3
"""Stop hook: run the fast unit tests before Claude finishes a turn.

Fails (exit 2, Claude keeps working) when tests fail. Skips when the hook
already fired this turn, or before the Python package exists.
"""

import json
import subprocess
import sys
from pathlib import Path


def failure_lines(output: str, limit: int = 15) -> list[str]:
    """Keep only FAILED/ERROR lines and the final summary, to save context tokens."""
    lines = [ln for ln in output.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    extra = len(lines) - limit
    if extra > 0:
        lines = [*lines[:limit], f"... {extra} more"]
    summary = [ln for ln in output.splitlines() if " passed" in ln or " failed" in ln]
    return lines + summary[-1:]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    if payload.get("stop_hook_active"):
        return 0
    root = Path(payload.get("cwd") or ".").resolve()
    if not (root / "pyproject.toml").exists():
        return 0
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "--tb=no", "-rfE", "-m", "not slow and not live"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=110,
        )
    except subprocess.TimeoutExpired:
        print(
            "Fast tests timed out after 110s; check for slow tests missing the 'slow' mark.",
            file=sys.stderr,
        )
        return 2
    # pytest exit 5 = no tests collected; not a failure.
    if result.returncode not in (0, 5):
        tail = "\n".join(failure_lines(result.stdout))
        print(
            f"Fast tests failed. Fix the cause before stopping:\n{tail}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
