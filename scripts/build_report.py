"""Build docs/report.pdf from docs/report.md: markdown -> HTML -> headless Chrome print.

uv run --group docs python scripts/build_report.py [--chrome PATH]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 10pt;
       line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 18pt 0 6pt; border-bottom: 1px solid #ccc; padding-bottom: 2pt; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; }
h4 { font-size: 10pt; margin: 10pt 0 4pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8pt;
        page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 3pt 4pt; vertical-align: top; text-align: left; }
th { background: #f0f0f0; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.5pt; background: #f4f4f4;
       padding: 0 2pt; }
img { max-width: 70%; max-height: 165mm; display: block; margin: 6pt auto; }
ul { padding-left: 16pt; }
"""


def find_chrome(explicit: str | None) -> str:
    for name in [explicit, "google-chrome", "chromium", "chromium-browser", "chrome"]:
        if name and shutil.which(name):
            return shutil.which(name)
    sys.exit("Chrome/Chromium not found; pass --chrome PATH")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome")
    args = ap.parse_args()
    body = markdown.markdown(
        (DOCS / "report.md").read_text(encoding="utf-8"), extensions=["tables", "sane_lists"]
    )
    html = (
        f'<!doctype html><html><head><meta charset="utf-8"><base href="{DOCS.as_uri()}/">'
        f"<title>guardbank report</title><style>{CSS}</style></head><body>{body}</body></html>"
    )
    out = DOCS / "report.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                find_chrome(args.chrome),
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={tmp}/profile",
                f"--print-to-pdf={out}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
