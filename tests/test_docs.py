"""Docs stay in sync with SPEC and eval results (spec delta: docs/specs/report.md)."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
REPORT = ROOT / "docs" / "report.md"
DOT = ROOT / "docs" / "architecture.dot"


def _routing_table(text: str) -> str:
    """The markdown table that starts with the routing-table header row."""
    lines = text.splitlines()
    header = "| Category | Example | Action |"
    start = next(i for i, ln in enumerate(lines) if ln.startswith(header))
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return "\n".join(lines[start:end])


def test_readme_routing_table_matches_spec():
    spec = (ROOT / "SPEC.md").read_text()
    assert _routing_table(README.read_text()) == _routing_table(spec)


def test_report_tables_are_current():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "report_tables.py"), "--check"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_report_has_required_sections():
    text = REPORT.read_text()
    headings = re.findall(r"^##\s+(.+)$", text, flags=re.M)
    for prefix in (
        "a. Design and architecture",
        "b. Implementation choices",
        "c. Evaluation results",
        "d. Risk assessment",
    ):
        assert any(h.startswith(prefix) for h in headings), prefix
    assert any(h.startswith("Failure analysis") for h in headings)
    assert any(h.startswith("Trade-offs") for h in headings)
    failure = text.split("## Failure analysis", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"^### ", failure, flags=re.M)) >= 2


def test_architecture_names_every_pipeline_stage():
    dot = DOT.read_text().lower()
    for stage in (
        "normalizer",
        "pii",
        "injection",
        "topic router",
        "retriever",
        "chunk scan",
        "llm",
        "schema",
        "groundedness",
        "sensitive-info",
        "remediation",
        "audit",
    ):
        assert stage in dot, stage
