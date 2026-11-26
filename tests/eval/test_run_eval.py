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
