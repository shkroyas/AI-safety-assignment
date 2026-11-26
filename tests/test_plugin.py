"""guardbank-dev plugin mirrors .claude/ (spec delta: docs/specs/plugin.md)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "guardbank-dev"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_plugin_copies_match_sources():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_plugin.py"), "--check"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_manifests_agree():
    manifest = _load(PLUGIN / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == "guardbank-dev"
    market = _load(MARKETPLACE)
    entry = next(p for p in market["plugins"] if p["name"] == "guardbank-dev")
    assert (ROOT / entry["source"]).resolve() == PLUGIN.resolve()
    assert entry["version"] == manifest["version"]


def test_hooks_mirror_project_settings():
    project = _load(ROOT / ".claude" / "settings.json")["hooks"]
    plugin = _load(PLUGIN / "hooks" / "hooks.json")["hooks"]
    assert set(plugin) == set(project)
    for event, groups in project.items():
        assert [g.get("matcher") for g in plugin[event]] == [g.get("matcher") for g in groups]
    for groups in plugin.values():
        for group in groups:
            for hook in group["hooks"]:
                cmd = hook["command"]
                assert "${CLAUDE_PLUGIN_ROOT}" in cmd, cmd
                script = cmd.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split('"', 1)[0]
                assert (PLUGIN / script).is_file(), script


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not on PATH")
@pytest.mark.parametrize("target", [PLUGIN, MARKETPLACE])
def test_claude_plugin_validate(target):
    proc = subprocess.run(
        ["claude", "plugin", "validate", "--strict", str(target)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
