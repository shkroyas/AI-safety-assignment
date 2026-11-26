"""Mirror .claude/ skills, agents and hooks into plugins/guardbank-dev/.

.claude/ is the single source; the plugin is generated.
  python scripts/sync_plugin.py          rewrite the plugin copies
  python scripts/sync_plugin.py --check  exit 1 if any copy is missing, stale or extra
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".claude"
PLUGIN = ROOT / "plugins" / "guardbank-dev"
MIRRORED = ["skills", "agents", "hooks"]  # directories copied file by file
PROJECT_HOOKS = '"$CLAUDE_PROJECT_DIR/.claude/hooks/'
PLUGIN_HOOKS = '"${CLAUDE_PLUGIN_ROOT}/hooks/'


def _files(base: Path) -> dict[str, bytes]:
    if not base.is_dir():
        return {}
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def hooks_json() -> bytes:
    """settings.json hooks with script paths moved under ${CLAUDE_PLUGIN_ROOT}."""
    hooks = json.loads((SRC / "settings.json").read_text())["hooks"]
    text = json.dumps({"hooks": hooks}, indent=2)
    if PROJECT_HOOKS.replace('"', '\\"') not in text:
        raise SystemExit("settings.json hooks no longer use $CLAUDE_PROJECT_DIR/.claude/hooks/")
    text = text.replace(PROJECT_HOOKS.replace('"', '\\"'), PLUGIN_HOOKS.replace('"', '\\"'))
    return (text + "\n").encode()


def expected() -> dict[str, bytes]:
    """Plugin-relative path -> content for every generated file."""
    out: dict[str, bytes] = {}
    for name in MIRRORED:
        out.update({f"{name}/{rel}": data for rel, data in _files(SRC / name).items()})
    out["hooks/hooks.json"] = hooks_json()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    want = expected()
    have = {
        f"{name}/{rel}": data
        for name in MIRRORED
        for rel, data in _files(PLUGIN / name).items()
    }
    problems = [f"missing or stale: {p}" for p, d in want.items() if have.get(p) != d]
    problems += [f"extra: {p}" for p in have if p not in want]
    if args.check:
        for line in problems:
            print(line)
        return 1 if problems else 0
    for name in MIRRORED:
        shutil.rmtree(PLUGIN / name, ignore_errors=True)
    for rel, data in want.items():
        dest = PLUGIN / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if rel.endswith(".py"):
            dest.chmod(0o755)
    print(f"synced {len(want)} files into {PLUGIN.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
