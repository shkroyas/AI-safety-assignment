#!/usr/bin/env python3
"""PreToolUse hook for Bash: block git actions this repo's workflow forbids.

Exit 2 blocks the tool call; stderr is shown to Claude as the reason.
Rules (SPEC.md §10): no direct push to main, no force-push, no commit-date
overrides, never stage .env files.
"""

import json
import re
import sys

RULES = [
    (
        re.compile(r"\bgit\s+push\b[^;&|]*?(\s|:)main\b"),
        "Direct push to main is not allowed. Push the feature branch and open a PR.",
    ),
    (
        re.compile(r"\bgit\s+push\b[^;&|]*\s(--force(-with-lease)?|-f)\b"),
        "Force-push is not allowed. Never rewrite pushed history.",
    ),
    (
        re.compile(r"\bGIT_(AUTHOR|COMMITTER)_DATE\s*="),
        "Commit-date overrides are not allowed. Commits carry real timestamps.",
    ),
    (
        re.compile(r"\bgit\s+commit\b[^;&|]*\s--date\b"),
        "Commit-date overrides are not allowed. Commits carry real timestamps.",
    ),
    (
        re.compile(r"\bgit\s+add\b[^;&|]*\s\S*\.env(?!\.example)(\.\w+)?(\s|$)"),
        "Never stage .env files; they hold secrets.",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    for pattern, reason in RULES:
        if pattern.search(command):
            print(f"Blocked by guard_bash hook: {reason}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
