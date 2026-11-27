"""Generate the metrics tables in docs/report.md and README.md from eval/results.

Blocks sit between `<!-- tables:<name> -->` and `<!-- /tables:<name> -->`.
  python scripts/report_tables.py          rewrite the blocks in place
  python scripts/report_tables.py --check  exit 1 if any block is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
TARGETS = [ROOT / "docs" / "report.md", ROOT / "README.md"]
BINARY_SETS = [
    "injection",
    "injection_pii",
    "crisis",
    "pii",
    "groundedness",
    "leakage",
    "leakage_pii",
    "chunk_poison",
]


def _load(path: Path) -> object:
    return json.loads(path.read_text())


def _ci(ci: list[float]) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _ids(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "—"


def cases_table() -> str:
    rows = _load(RESULTS / "full" / "cases.json")
    summary = _load(RESULTS / "full" / "summary.json")
    fast = _load(RESULTS / "fast" / "summary.json")
    total, passed = Counter(), Counter()
    for r in rows:
        total[r["category"]] += 1
        passed[r["category"]] += r["pass"]
    out = ["| category | cases | passed (full mode) |", "|---|---|---|"]
    out += [f"| {c} | {total[c]} | {passed[c]} |" for c in total]
    c = summary["cases"]
    out.append(f"| **total** | **{c['total']}** | **{c['passed']}** |")
    out += [
        "",
        f"Full mode failed: {_ids(c['failed'])}. "
        f"Fast mode (stubs): {fast['cases']['passed']}/{fast['cases']['total']} passed, "
        f"failed: {_ids(fast['cases']['failed'])}.",
    ]
    return "\n".join(out)


def metrics_table() -> str:
    s = _load(RESULTS / "full" / "summary.json")
    out = [
        "| guardrail | n | P (95% CI) | R (95% CI) | F1 | FPR (95% CI) | FP ids | FN ids |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in BINARY_SETS:
        t = s["sets"][name]["test"]
        out.append(
            f"| {name} | {t['n']} | {t['precision']:.3f} {_ci(t['ci']['precision'])} "
            f"| {t['recall']:.3f} {_ci(t['ci']['recall'])} | {t['f1']:.3f} "
            f"| {t['fpr']:.3f} {_ci(t['ci']['fpr'])} | {_ids(t['fp_ids'])} | {_ids(t['fn_ids'])} |"
        )
    topics = s["sets"]["topics"]["test"]
    b = topics["binary"]
    out += [
        "",
        f"Topics (test, n={topics['n']}): accuracy {topics['accuracy']:.3f}, "
        f"macro-F1 {topics['macro_f1']:.3f}, crisis recall {topics['crisis_recall']:.3f}. "
        f"Sensitive vs normal: P {b['precision']:.3f}, R {b['recall']:.3f} "
        f"{_ci(b['ci']['recall'])}, FN {_ids(b['fn_ids'])}.",
        "",
        "| topic | P | R (95% CI) | FP ids | FN ids |",
        "|---|---|---|---|---|",
    ]
    for cls, m in topics["per_class"].items():
        out.append(
            f"| {cls} | {m['precision']:.3f} | {m['recall']:.3f} {_ci(m['ci']['recall'])} "
            f"| {_ids(m['fp_ids'])} | {_ids(m['fn_ids'])} |"
        )
    out += ["", f"Run: full mode, commit `{s['commit'][:7]}`, test split (70%)."]
    return "\n".join(out)


def ablations_table() -> str:
    text = (RESULTS / "ablations" / "tables.md").read_text()
    body = text.split("\n", 1)[1].strip()  # drop the file's own H1
    return re.sub(r"^## ", "#### ", body, flags=re.M)


RENDERERS = {"cases": cases_table, "metrics": metrics_table, "ablations": ablations_table}
BLOCK = re.compile(r"(<!-- tables:(\w+) -->\n)(.*?)(<!-- /tables:\2 -->)", re.S)


def render(text: str) -> str:
    return BLOCK.sub(lambda m: m.group(1) + RENDERERS[m.group(2)]() + "\n" + m.group(4), text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    stale = []
    for path in TARGETS:
        if not path.exists():
            stale.append(f"{path.name}: missing")
            continue
        old = path.read_text()
        names = [m.group(2) for m in BLOCK.finditer(old)]
        unknown = [n for n in names if n not in RENDERERS]
        if unknown:
            stale.append(f"{path.name}: unknown blocks {unknown}")
            continue
        if not names:
            stale.append(f"{path.name}: no table blocks")
            continue
        new = render(old)
        if new != old:
            if args.check:
                stale.append(f"{path.name}: stale tables")
            else:
                path.write_text(new)
    for line in stale:
        print(line)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
