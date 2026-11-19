#!/usr/bin/env python3
"""PostToolUse hook for Edit/Write: ruff-format and auto-fix edited Python files.

Exit 2 (shown to Claude) only when lint errors remain that ruff cannot fix.
"""

import json
import shutil
import subprocess
import sys


def ruff_cmd() -> list[str]:
    return ["ruff"] if shutil.which("ruff") else ["uvx", "ruff"]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = payload.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        return 0
    ruff = ruff_cmd()
    subprocess.run([*ruff, "format", "--quiet", path], check=False)
    check = subprocess.run(
        [*ruff, "check", "--fix", "--quiet", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        print(
            f"ruff found issues it could not fix in {path}:\n{check.stdout}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
