"""Ablations, threshold sweeps, latency and charts: `make ablations` (needs the `ml` extra).

Writes eval/results/ablations/{ablations,sweeps,latency}.json, tables.md and charts/*.png.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from guardbank.evaluation.ablations import run_ablations

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["fast", "full"], default="full")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "ablations")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    run_ablations(args.mode, args.out, repeats=args.repeats)
    print((args.out / "tables.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
