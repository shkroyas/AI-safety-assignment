"""Run the guardbank evaluation: `make eval` (fast, stubs) or `make eval-full` (real models).

Writes eval/results/<mode>/summary.json, errors.md and cases.json, then prints the test-split table.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from guardbank.evaluation.run import run

ROOT = Path(__file__).resolve().parents[1]


def _fmt(x: float | None) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def main() -> None:
    load_dotenv(ROOT / ".env")  # HF_TOKEN for gated models; by path, not cwd search
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or ROOT / "eval" / "results" / args.mode
    summary = run(args.mode, out)
    print(f"mode={summary['mode']} commit={summary['commit']} dirty={summary['dirty']}")
    print(f"{'set (test split)':18} {'n':>4} {'P':>6} {'R':>6} {'F1':>6} {'FPR':>6}  FP FN")
    for name, parts in summary["sets"].items():
        m = parts["test"]["binary"] if name == "topics" else parts["test"]
        print(
            f"{name:18} {m['n']:>4} {_fmt(m['precision']):>6} {_fmt(m['recall']):>6} "
            f"{_fmt(m['f1']):>6} {_fmt(m['fpr']):>6}  {m['fp']:>2} {m['fn']:>2}"
        )
    t = summary["sets"]["topics"]["test"]
    print(f"topics macro F1 {_fmt(t['macro_f1'])}, crisis recall {_fmt(t['crisis_recall'])}")
    c = summary["cases"]
    print(f"cases {c['passed']}/{c['total']} pass; known failures {c['known_failures']}")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
