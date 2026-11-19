import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spec_section.sh"


def run(*args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=ROOT
    )


def test_prints_only_the_requested_section():
    out = run("3. Input guardrails").stdout
    assert out.startswith("## 3. Input guardrails")
    assert "Routing table" in out
    assert "## 4. Output guardrails" not in out


def test_includes_subsections_until_next_top_level_heading():
    out = run("4. Output guardrails").stdout
    assert "### Invalid-response policy" in out
    assert "## 5." not in out


def test_unknown_heading_fails():
    result = run("99. Nope")
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_other_file_can_be_given():
    out = run("1. Package and tooling", "docs/specs/skeleton.md").stdout
    assert "pyproject.toml" in out and "## 2." not in out
