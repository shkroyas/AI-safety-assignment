"""Ablations, threshold sweeps and latency (SPEC §6, docs/specs/eval-ablations.md).

Thresholds are chosen on the dev split only; the YAML is never changed here. In `fast` mode
every ML kind is replaced by its stub, so the run checks structure without loading weights.
"""

from __future__ import annotations

import copy
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from guardbank.audit import AuditLog
from guardbank.cases import Case, CaseLLM, load_cases
from guardbank.config import DEFAULT_CONFIG, ROOT, Settings, load_settings
from guardbank.evaluation.datasets import load_set, split_ids
from guardbank.evaluation.metrics import binary_metrics
from guardbank.evaluation.runners import run_injection, settings_for
from guardbank.output.groundedness import GroundednessChecker
from guardbank.output.schema import SupportReply
from guardbank.pipeline import Pipeline, Session
from guardbank.rag.llm import MockLLM

GRID = [round(0.05 * i, 2) for i in range(1, 20)]
PARTS = ("dev", "test")
Row = tuple[str, int, float, dict[str, Any]]
_KEYS = ("precision", "recall", "f1", "fpr", "tp", "fp", "fn", "tn")


# ---------- generic helpers ----------


def sweep(
    rows: Iterable[Row], taus: Iterable[float], predict: Callable[[float, dict, float], bool]
) -> list[dict[str, Any]]:
    rows = list(rows)
    out = []
    for tau in taus:
        m = binary_metrics(
            (i, label, int(predict(score, extra, tau))) for i, label, score, extra in rows
        )
        out.append({"tau": tau, **{k: m[k] for k in _KEYS}})
    return out


def best_tau(sweep_rows: list[dict[str, Any]], current: float) -> float:
    """Max F1; ties go to the tau closest to the current one. No defined F1 -> current."""
    scored = [r for r in sweep_rows if r["f1"] is not None]
    if not scored:
        return current
    top = max(r["f1"] for r in scored)
    return min((r for r in scored if r["f1"] == top), key=lambda r: abs(r["tau"] - current))["tau"]


def percentile(values: Iterable[float], q: float) -> float:
    v = sorted(values)
    if not v:
        return 0.0
    k = (len(v) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


# ---------- variants ----------


def injection_variants(s: Settings) -> dict[str, Settings]:
    regex, clf, hybrid, both = (copy.deepcopy(s) for _ in range(4))
    for v in (regex, clf, hybrid):
        v.input["injection"]["classifier_redacted"] = False
    regex.input["injection"]["classifier"] = "stub"
    clf.input["injection"]["classifier"] = "deberta"
    clf.input["injection"]["patterns"] = {}
    hybrid.input["injection"]["classifier"] = "deberta"
    both.input["injection"]["classifier"] = "deberta"
    both.input["injection"]["classifier_redacted"] = True
    return {"regex": regex, "classifier": clf, "hybrid": hybrid, "hybrid+both-flag": both}


def groundedness_variants(s: Settings) -> dict[str, Settings]:
    out = {}
    for name, scorer, number in [
        ("keyword", "keyword", False),
        ("keyword+number", "keyword", True),
        ("nli", "hhem", False),
        ("nli+number", "hhem", True),
    ]:
        v = copy.deepcopy(s)
        v.output["groundedness"]["scorer"] = scorer
        v.output["groundedness"]["number_check"] = number
        out[name] = v
    return out


def _stubify(s: Settings) -> Settings:
    """Fast mode: same structure, no weights."""
    s = copy.deepcopy(s)
    s.input["injection"]["classifier"] = "stub"
    s.input["pii"]["backend"] = "stub"
    s.input["topics"]["classifier"] = "stub"
    s.output["groundedness"]["scorer"] = "keyword"
    s.output["leakage"]["embedder"] = "hashing"
    s.retriever.embedder = "hashing"
    return s


# ---------- per-item scores ----------


def _split_rows(rows: list[Row]) -> dict[str, list[Row]]:
    sp = split_ids([(r[0], r[1]) for r in rows])
    return {part: [r for r in rows if sp[r[0]] == part] for part in PARTS}


def _metrics_by_part(rows: list[Row], predict, tau) -> dict[str, Any]:
    return {
        part: binary_metrics((i, lab, int(predict(sc, ex, tau))) for i, lab, sc, ex in part_rows)
        for part, part_rows in _split_rows(rows).items()
    }


def injection_rows(s: Settings, name: str = "injection") -> list[Row]:
    preds = run_injection(load_set(name), s)
    return [(p.id, int(p.label), float(p.score), {}) for p in preds]


def groundedness_rows(s: Settings) -> list[Row]:
    """score = lowest claim score; extra.missing = a number/date is absent from the evidence."""
    checker = GroundednessChecker.from_settings(s)
    rows = []
    for it in load_set("groundedness"):
        chunks = {f"ev#{i}": t for i, t in enumerate(it.evidence)}
        reply = SupportReply(
            answer=it.claim, citations=list(chunks), intent="other", confidence=0.5, escalate=False
        )
        claims = checker.check(reply, chunks).details.get("claims", [])
        score = min((c["score"] for c in claims), default=0.0)
        missing = any(c["numbers_missing"] for c in claims)
        rows.append((it.id, int(it.label), float(score), {"missing": missing}))
    return rows


def _fires(score: float, extra: dict, tau: float) -> bool:
    return score >= tau


def _unsupported(number_check: bool):
    def predict(score: float, extra: dict, tau: float) -> bool:
        return score < tau or (number_check and extra.get("missing", False))

    return predict


# ---------- sweeps ----------


def _sweep_report(rows: list[Row], predict, current: float) -> dict[str, Any]:
    parts = _split_rows(rows)
    taus = sorted(set(GRID) | {current})
    dev_curve = sweep(parts["dev"], taus, predict)
    dev_best = best_tau(dev_curve, current)
    at = {r["tau"]: r for r in sweep(parts["test"], taus, predict)}
    return {
        "current": current,
        "dev_best": dev_best,
        "test_at_current": at[current],
        "test_at_dev_best": at[dev_best],
        "dev_curve": dev_curve,
        "test_curve": list(at.values()),
    }


# ---------- latency ----------


def latency(s: Settings, cases: list[Case], repeats: int = 3, warmup: int = 1) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        pipeline = Pipeline.from_settings(s, llm=MockLLM(), audit=AuditLog(Path(tmp) / "a.jsonl"))
        totals: list[float] = []
        stages: dict[str, list[float]] = {}
        for n in range(warmup + repeats):
            for case in cases:
                pipeline.llm = CaseLLM(case.llm_output) if case.llm_output else MockLLM()
                r = pipeline.run(case.input, Session())
                if n < warmup:
                    continue
                totals.append(r.latency_ms)
                for st in r.stages:
                    if st.stage != "remediation":
                        stages.setdefault(st.stage, []).append(st.latency_ms)
    q = lambda v: {"p50": percentile(v, 50), "p95": percentile(v, 95)}  # noqa: E731
    return {
        "n": len(cases),
        "repeats": repeats,
        "total": q(totals),
        "stages": {k: q(v) for k, v in stages.items()},
    }


def hardware() -> dict[str, Any]:
    info: dict[str, Any] = {"python": platform.python_version(), "cpu": platform.processor()}
    try:
        import torch

        info["torch"] = torch.__version__
        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except ImportError:
        info["torch"] = info["gpu"] = None
    return info


def _latency_mode(mode: str, base: Settings, cases: list[Case], repeats: int) -> dict[str, Any]:
    if mode == "fast":
        return {**latency(base, cases, repeats), "hardware": hardware()}
    if mode == "full-gpu":
        return {**latency(settings_for(base, "full"), cases, repeats), "hardware": hardware()}
    if mode == "full-cpu":  # separate process: cached GPU models must not leak into the CPU run
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lat.json"
            env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
            cmd = [
                sys.executable,
                "-m",
                "guardbank.evaluation.ablations",
                "full-cpu",
                str(out),
                str(repeats),
            ]
            subprocess.run(cmd, env=env, check=True, cwd=ROOT)
            return json.loads(out.read_text())
    raise ValueError(f"unknown latency mode {mode!r}")


# ---------- orchestration ----------


def _tables(abl: dict, sweeps: dict, lat: dict) -> str:
    f = lambda x: "–" if x is None else f"{x:.3f}"  # noqa: E731
    ci = lambda c: "–" if c is None else f"[{c[0]:.2f}, {c[1]:.2f}]"  # noqa: E731
    out = ["# Ablations, sweeps and latency", ""]
    for name, variants in abl.items():
        out += [
            f"## {name} ablation (test split)",
            "",
            "| variant | P | R (95% CI) | F1 | FPR (95% CI) | FP | FN |",
            "|---|---|---|---|---|---|---|",
        ]
        for v, parts in variants.items():
            m = parts["test"]
            out.append(
                f"| {v} | {f(m['precision'])} | {f(m['recall'])} {ci(m['ci']['recall'])} | "
                f"{f(m['f1'])} | {f(m['fpr'])} {ci(m['ci']['fpr'])} | {m['fp']} | {m['fn']} |"
            )
        out.append("")
    out += [
        "## Threshold sweeps (chosen on dev, reported on test)",
        "",
        "| sweep | current | dev-best | test F1 @current | test F1 @dev-best "
        "| test FPR @current | test FPR @dev-best |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in sweeps.items():
        a, b = s["test_at_current"], s["test_at_dev_best"]
        out.append(
            f"| {name} | {s['current']} | {s['dev_best']} | {f(a['f1'])} | {f(b['f1'])} | "
            f"{f(a['fpr'])} | {f(b['fpr'])} |"
        )
    out += [
        "",
        "## Latency (ms, MockLLM: LLM time excluded)",
        "",
        "| mode | p50 | p95 | hardware |",
        "|---|---|---|---|",
    ]
    for mode, m in lat["modes"].items():
        hw = "stubs, no models" if mode == "fast" else (m["hardware"].get("gpu") or "CPU only")
        out.append(f"| {mode} | {m['total']['p50']:.1f} | {m['total']['p95']:.1f} | {hw} |")
    return "\n".join(out) + "\n"


def run_ablations(
    mode: str,
    out_dir: str | Path,
    *,
    charts: bool = True,
    latency_modes: tuple[str, ...] = ("fast", "full-gpu", "full-cpu"),
    repeats: int = 3,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = load_settings(DEFAULT_CONFIG, env={})
    shape = (lambda s: s) if mode == "full" else _stubify
    full = shape(settings_for(base, "full"))

    abl: dict[str, Any] = {"injection": {}, "injection_pii": {}, "groundedness": {}}
    inj_rows: dict[str, list[Row]] = {}
    for name, v in injection_variants(full).items():
        v = shape(v)
        tau = v.input["injection"]["tau"]
        inj_rows[name] = injection_rows(v)
        abl["injection"][name] = _metrics_by_part(inj_rows[name], _fires, tau)
        abl["injection_pii"][name] = _metrics_by_part(
            injection_rows(v, "injection_pii"), _fires, tau
        )
    g_rows: dict[str, list[Row]] = {}
    for name, v in groundedness_variants(full).items():
        v = shape(v)
        g = v.output["groundedness"]
        tau_g = g.get(g["scorer"], {}).get("tau_g", g["tau_g"])
        g_rows[name] = groundedness_rows(v)
        abl["groundedness"][name] = _metrics_by_part(
            g_rows[name], _unsupported(g["number_check"]), tau_g
        )

    g = base.output["groundedness"]
    sweeps = {
        "injection_tau": _sweep_report(
            inj_rows["hybrid+both-flag"], _fires, base.input["injection"]["tau"]
        ),
        "tau_g_keyword": _sweep_report(g_rows["keyword+number"], _unsupported(True), g["tau_g"]),
    }
    if mode == "full":
        sweeps["tau_g_hhem"] = _sweep_report(
            g_rows["nli+number"], _unsupported(True), g["hhem"]["tau_g"]
        )

    cases = load_cases(ROOT / "tests" / "cases.yaml")
    lat = {"modes": {m: _latency_mode(m, base, cases, repeats) for m in latency_modes}}

    for fname, data in [("ablations.json", abl), ("sweeps.json", sweeps), ("latency.json", lat)]:
        (out_dir / fname).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (out_dir / "tables.md").write_text(_tables(abl, sweeps, lat), encoding="utf-8")
    if charts:
        from guardbank.evaluation.charts import write_charts

        write_charts(abl, sweeps, lat, out_dir / "charts")
    return {"ablations": abl, "sweeps": sweeps, "latency": lat}


if __name__ == "__main__":  # used for the isolated full-cpu latency run
    _mode, _out, _repeats = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
    _base = load_settings(DEFAULT_CONFIG, env={})
    _cases = load_cases(ROOT / "tests" / "cases.yaml")
    _res = {**latency(settings_for(_base, "full"), _cases, _repeats), "hardware": hardware()}
    _out.write_text(json.dumps(_res), encoding="utf-8")
