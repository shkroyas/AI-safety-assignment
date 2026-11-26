"""Run every labeled set and the e2e cases; write summary.json, errors.md and cases.json."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from guardbank.audit import AuditLog
from guardbank.cases import load_cases, run_case
from guardbank.config import DEFAULT_CONFIG, ROOT, load_settings
from guardbank.evaluation.datasets import EVAL_DIR, SETS, load_set, split_ids
from guardbank.evaluation.metrics import binary_metrics, multiclass_metrics
from guardbank.evaluation.runners import RUNNERS, Prediction, models_used, settings_for
from guardbank.pipeline import Pipeline
from guardbank.rag.llm import MockLLM

PARTS = ("dev", "test")


def _commit() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    # The eval's own output does not make the code dirty.
    dirty = bool(git("status", "--porcelain", "--", ".", ":!eval/results"))
    return {"sha": git("rev-parse", "HEAD") or None, "dirty": dirty}


def _set_metrics(name: str, preds: list[Prediction], classes: list[str]) -> dict[str, Any]:
    if name == "topics":
        rows = [(p.id, p.label, p.pred) for p in preds]
        m = multiclass_metrics(rows, classes)
        m["binary"] = binary_metrics(
            (p.id, int(p.label != "NORMAL"), int(p.pred != "NORMAL")) for p in preds
        )
        crisis = m["per_class"]["CRISIS"]
        m["crisis_recall"] = crisis["recall"]
        return m
    m = binary_metrics((p.id, int(p.label), int(p.pred)) for p in preds)
    if name == "pii":
        per_label: dict[str, list[int]] = {}
        for p in preds:
            for label in p.extra["expected"]:
                per_label.setdefault(label, []).append(int(label in p.extra["found"]))
        m["per_label_recall"] = {k: sum(v) / len(v) for k, v in sorted(per_label.items())}
    return m


def _errors_md(mode: str, commit: dict[str, Any], results: dict[str, list[Prediction]], sp) -> str:
    lines = [f"# Errors ({mode} mode, commit {commit['sha'] or 'unknown'})", ""]
    for name, preds in results.items():
        for part in PARTS:
            if name == "topics":
                wrong = [p for p in preds if sp[name][p.id] == part and p.pred != p.label]
                head = "| id | gold | predicted | score | text |"
                rows = [
                    f"| {p.id} | {p.label} | {p.pred} | {p.score:.2f} | {p.text[:80]} |"
                    for p in wrong
                ]
            else:
                wrong = [p for p in preds if sp[name][p.id] == part and int(p.pred) != int(p.label)]
                head = "| id | error | kind | score | text |"
                rows = [
                    f"| {p.id} | {'FN' if p.label else 'FP'} | {p.kind} | {p.score:.2f} | "
                    f"{p.text[:80].replace('|', '/').replace(chr(10), ' ')} |"
                    for p in wrong
                ]
            lines += [f"## {name} ({part}): {len(wrong)} errors", ""]
            lines += [head, "|---|---|---|---|---|", *rows, ""] if rows else ["None.", ""]
    return "\n".join(lines)


def _run_cases(settings, out_dir: Path) -> list[dict[str, Any]]:
    pipeline = Pipeline.from_settings(
        settings, llm=MockLLM(), audit=AuditLog(out_dir / "cases_audit.jsonl")
    )
    rows = []
    for case in load_cases(ROOT / "tests" / "cases.yaml"):
        r = run_case(pipeline, case)
        rows.append(
            {
                "id": r.id,
                "category": case.category,
                "pass": r.passed,
                "actual": r.actual,
                "reasons": r.reasons,
                "known_failure": case.known_failure,
            }
        )
    (out_dir / "cases_audit.jsonl").unlink(missing_ok=True)
    return rows


def run(mode: str, out_dir: str | Path, data_dir: Path = EVAL_DIR) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = settings_for(load_settings(DEFAULT_CONFIG, env={}), mode)
    classes = list(settings.input["topics"]["routes"])
    commit = _commit()

    results: dict[str, list[Prediction]] = {}
    splits: dict[str, dict[str, str]] = {}
    summary_sets: dict[str, Any] = {}
    for name in SETS:
        preds = RUNNERS[name](load_set(name, data_dir), settings)
        sp = split_ids([(p.id, p.label) for p in preds])
        results[name], splits[name] = preds, sp
        summary_sets[name] = {
            part: _set_metrics(name, [p for p in preds if sp[p.id] == part], classes)
            for part in PARTS
        }

    cases = _run_cases(settings, out_dir)
    summary = {
        "mode": mode,
        "commit": commit["sha"],
        "dirty": commit["dirty"],
        "config_sha256": hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
        "models": models_used(settings),
        "sets": summary_sets,
        "cases": {
            "total": len(cases),
            "passed": sum(c["pass"] for c in cases),
            "known_failures": [c["id"] for c in cases if c["known_failure"]],
            "failed": [c["id"] for c in cases if not c["pass"]],
        },
    }
    summary = json.loads(json.dumps(summary))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "cases.json").write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    (out_dir / "errors.md").write_text(_errors_md(mode, commit, results, splits), encoding="utf-8")
    return summary
