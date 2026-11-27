"""Fast-mode eval run writes the documented outputs (docs/specs/eval.md)."""

import json

from guardbank.evaluation.datasets import SETS, load_set
from guardbank.evaluation.run import run


def test_fast_run_outputs(tmp_path):
    summary = run("fast", tmp_path)
    for f in ("summary.json", "errors.md", "cases.json"):
        assert (tmp_path / f).exists(), f
    on_disk = json.loads((tmp_path / "summary.json").read_text())
    assert on_disk == summary
    assert summary["mode"] == "fast"
    assert len(summary["config_sha256"]) == 64
    assert "commit" in summary
    for name in SETS:
        ids = {it.id for it in load_set(name)}
        for part in ("dev", "test"):
            m = summary["sets"][name][part]
            core = m["binary"] if name == "topics" else m
            for key in ("precision", "recall", "f1", "fpr", "ci", "fp_ids", "fn_ids", "n"):
                assert key in core, (name, part, key)
            if name != "chunk_poison":
                assert set(core["fp_ids"]) | set(core["fn_ids"]) <= ids
    assert "macro_f1" in summary["sets"]["topics"]["test"]
    cases = json.loads((tmp_path / "cases.json").read_text())
    assert len(cases) >= 40 and {"id", "pass", "actual"} <= set(cases[0])
    errors = (tmp_path / "errors.md").read_text()
    assert "# Errors" in errors


def test_cases_json_records_the_full_case(tmp_path):
    """docs/specs/docs-per-case-table.md: every field the assignment asks for, per case."""
    import yaml

    from guardbank.evaluation.run import ROOT

    run("fast", tmp_path)
    rows = {r["id"]: r for r in json.loads((tmp_path / "cases.json").read_text())}
    cases = yaml.safe_load((ROOT / "tests" / "cases.yaml").read_text(encoding="utf-8"))
    assert set(rows) == {c["id"] for c in cases}
    for c in cases:
        row = rows[c["id"]]
        for key in ("input", "reference", "expected", "actual", "reply", "pass", "reasons"):
            assert key in row, (c["id"], key)
        assert row["input"] == c["input"]
        if c.get("reference_docs") or c.get("llm_output"):
            assert row["reference"] != "—", c["id"]


def test_pii_summary_has_entity_metrics(tmp_path):
    """docs/specs/fix-entity-pii-metrics.md."""
    summary = run("fast", tmp_path)
    for part in ("dev", "test"):
        ent = summary["sets"]["pii"][part]["entity"]
        for key in ("precision", "recall", "f1", "ci", "fp_entities", "fn_entities", "per_label"):
            assert key in ent, (part, key)
