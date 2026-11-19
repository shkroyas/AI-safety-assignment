"""Tests for the PreToolUse Bash guard hook (.claude/hooks/guard_bash.py)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard_bash.py"


def run_hook(command: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        check=False,
        text=True,
    )


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push -u origin main",
        "git push origin HEAD:main",
        "git push --force origin feat/x",
        "git push -f origin feat/x",
        "git push --force-with-lease",
        "GIT_COMMITTER_DATE='2026-10-13' git commit -m x",
        "GIT_AUTHOR_DATE=2026-10-13 git commit -m x",
        "git commit --date '2026-10-13' -m x",
        "git commit --amend --no-edit --date=now",
        "git add .env",
        "git add -f .env.local",
        "git rebase -i HEAD~3 && git push --force",
    ],
)
def test_blocks_dangerous_commands(command):
    result = run_hook(command)
    assert result.returncode == 2, command
    assert result.stderr.strip()


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin feat/input-guardrails",
        "git push origin chore/claude-code-setup",
        "git commit -m 'feat: add pii recognizer'",
        "git add src/guardbank/input/pii.py",
        "git add .env.example",
        "uv run pytest -q",
        "git log --format='%ad' --date=iso",
        "grep -r maintain src/",
    ],
)
def test_allows_normal_commands(command):
    result = run_hook(command)
    assert result.returncode == 0, (command, result.stderr)


def test_ignores_non_bash_payload():
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "x.py"}}),
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
