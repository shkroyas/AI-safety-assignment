"""Static PNG charts for the ablation run (docs/specs/eval-ablations.md); `ml` extra.

Palette: categorical slots 1-4 of the dataviz reference palette, validated for CVD separation
in light and dark mode. Light-mode slots 2-4 are under 3:1 contrast, so every chart carries
direct value labels and tables.md is the table view. Each chart is written in both modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

THEMES = {
    "light": {
        "surface": "#ffffff",
        "text": "#191919",
        "muted": "#666666",
        "grid": "#e6e6e6",
        "series": ["#257de0", "#f47230", "#00b894", "#f2a600"],
    },
    "dark": {
        "surface": "#191919",
        "text": "#efefef",
        "muted": "#9c9c9c",
        "grid": "#333333",
        "series": ["#338ced", "#e76624", "#00a888", "#d28e05"],
    },
}


def _axes(plt, theme: dict[str, Any], title: str, w: float = 7.0, h: float = 4.2):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme["grid"])
    ax.tick_params(colors=theme["muted"], labelsize=9)
    ax.grid(axis="y", color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, color=theme["text"], fontsize=11, loc="left", pad=12)
    return fig, ax


def _legend(ax, theme):
    leg = ax.legend(frameon=False, fontsize=9, loc="lower left", ncol=4, bbox_to_anchor=(0, -0.28))
    for t in leg.get_texts():
        t.set_color(theme["text"])


def _sweep(plt, name: str, s: dict[str, Any], theme: dict[str, Any], path: Path) -> None:
    curve = s["dev_curve"]
    fig, ax = _axes(
        plt, theme, f"{name}: dev-split sweep (current {s['current']}, dev-best {s['dev_best']})"
    )
    taus = [r["tau"] for r in curve]
    ends = []
    for i, key in enumerate(("precision", "recall", "f1")):
        ys = [r[key] if r[key] is not None else float("nan") for r in curve]
        ax.plot(taus, ys, color=theme["series"][i], linewidth=2, label=key)
        last = next(
            ((t, y) for t, y in zip(reversed(taus), reversed(ys), strict=True) if y == y), None
        )
        if last:
            ends.append([last[1], last[0], key])
    # Direct end labels, nudged apart so overlapping curves never overprint (min gap 0.06).
    ends.sort()
    for k in range(1, len(ends)):
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 0.06)
    for y, t, key in ends:
        ax.annotate(
            key,
            (t, y),
            xytext=(6, 0),
            textcoords="offset points",
            color=theme["text"],
            fontsize=8,
            va="center",
        )
    for tau, label in ((s["current"], "current"), (s["dev_best"], "dev-best")):
        ax.axvline(tau, color=theme["muted"], linewidth=1, linestyle="--")
        ax.annotate(
            label,
            (tau, 1.02),
            xytext=(3, 0),
            textcoords="offset points",
            color=theme["muted"],
            fontsize=8,
            ha="left",
            xycoords=("data", "axes fraction"),
        )
    ax.set_xlabel("threshold", color=theme["muted"], fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_xlim(0, 1.12)
    _legend(ax, theme)
    fig.tight_layout()
    fig.savefig(path, facecolor=theme["surface"])
    plt.close(fig)


def _ablation(plt, name: str, variants: dict[str, Any], theme: dict[str, Any], path: Path) -> None:
    fig, ax = _axes(plt, theme, f"{name} ablation, test split: recall and FPR with Wilson 95% CI")
    names = list(variants)
    width, gap = 0.36, 0.02
    for j, key in enumerate(("recall", "fpr")):
        xs = [i + (j - 0.5) * (width + gap) for i in range(len(names))]
        vals = [variants[n]["test"][key] for n in names]
        cis = [variants[n]["test"]["ci"][key] for n in names]
        ys = [v if v is not None else 0 for v in vals]
        err = [
            [max(y - c[0], 0) if c else 0 for y, c in zip(ys, cis, strict=True)],
            [max(c[1] - y, 0) if c else 0 for y, c in zip(ys, cis, strict=True)],
        ]
        ax.bar(
            xs,
            ys,
            width=width,
            color=theme["series"][j],
            label=key.upper() if key == "fpr" else key,
        )
        ax.errorbar(xs, ys, yerr=err, fmt="none", ecolor=theme["muted"], elinewidth=1, capsize=3)
        for x, y, v, c in zip(xs, ys, vals, cis, strict=True):
            top = c[1] if c else y  # label sits above the CI whisker, in the text ink
            ax.annotate(
                "–" if v is None else f"{v:.2f}",
                (x, top),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=theme["text"],
            )
    ax.set_xticks(range(len(names)), names)
    ax.set_ylim(0, 1.12)
    _legend(ax, theme)
    fig.tight_layout()
    fig.savefig(path, facecolor=theme["surface"])
    plt.close(fig)


def _latency(plt, lat: dict[str, Any], theme: dict[str, Any], path: Path) -> None:
    modes = list(lat["modes"])
    fig, ax = _axes(plt, theme, "Pipeline latency per request (ms, log scale; LLM time excluded)")
    width, gap = 0.36, 0.02
    for j, key in enumerate(("p50", "p95")):
        xs = [i + (j - 0.5) * (width + gap) for i in range(len(modes))]
        ys = [lat["modes"][m]["total"][key] for m in modes]
        ax.bar(xs, ys, width=width, color=theme["series"][j], label=key)
        for x, y in zip(xs, ys, strict=True):
            ax.annotate(
                f"{y:.1f}",
                (x, y),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=theme["text"],
            )
    ax.set_yscale("log")
    ax.set_xticks(range(len(modes)), modes)
    _legend(ax, theme)
    fig.tight_layout()
    fig.savefig(path, facecolor=theme["surface"])
    plt.close(fig)


def write_charts(abl: dict, sweeps: dict, lat: dict, out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for mode, theme in THEMES.items():
        for name, s in sweeps.items():
            p = out_dir / f"sweep_{name}_{mode}.png"
            _sweep(plt, name, s, theme, p)
            written.append(p)
        for name, variants in abl.items():
            p = out_dir / f"ablation_{name}_{mode}.png"
            _ablation(plt, name, variants, theme, p)
            written.append(p)
        p = out_dir / f"latency_{mode}.png"
        _latency(plt, lat, theme, p)
        written.append(p)
    return written
