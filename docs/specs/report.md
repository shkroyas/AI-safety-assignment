# Spec delta: docs/report

SPEC section: assignment deliverables 3–5 (report, architecture diagram, README). No guardrail code changes. ≤40 lines.

## Scope
- `docs/architecture.dot` (graphviz source) → `docs/architecture.png` + `.svg`: input stages, retriever + chunk scan,
  LLM, output stages, remediation, audit log, with the action each stage can take.
- `docs/report.md` → `docs/report.pdf`, in assignment order: a. Design and architecture, b. Implementation choices,
  c. Evaluation results (e2e table summary, per-guardrail P/R/F1/FPR with Wilson CI, FP/FN ids, ablations, latency),
  d. Risk assessment (OWASP LLM Top 10 + NIST AI RMF table, deployment verdict). Plus failure analysis and trade-offs.
- README rewritten: setup, `make` targets, curl + Python examples for `/chat`, MCP usage, routing table (verbatim from
  SPEC §3), design decisions, results summary linking the report.

## Behaviour
- Metrics tables are generated, not hand-typed: `scripts/report_tables.py` reads `eval/results/{full,ablations}` and
  rewrites the blocks between `<!-- tables:<name> -->` / `<!-- /tables:<name> -->` markers in the report and README.
- Failure analysis (≥2, each: why, consequence, improvement): 1) GLiNER generic nouns hid a crisis message — fixed in
  #19, before/after metrics; 2) injection lookalike FPs (INJE-037…044, score 1.00) — benign "ignore my previous
  question" refused; 3) topic misses TOPE-007 (crisis) and INJE-036 (Romanized Nepali) — analysed, not fixed.
- Trade-offs: strict = lookalike refusals at τ (usability cost, from the τ sweep); loose = keyword-only groundedness or
  regex-only injection (risk shown by the ablation numbers).
- Verdict, as I expect it from the numbers: "suitable only with restrictions" (human-reviewed pilot, crisis routing
  not relied on alone). Final wording follows the numbers.
- `make docs` builds diagram (`dot`) and PDF (markdown → HTML → headless Chrome `--print-to-pdf`).

## Config
- None. New dev dependency: `markdown` (docs group only).

## Tests first (`tests/test_docs.py`, fast)
- README routing table equals the SPEC §3 table byte for byte.
- `report_tables.py --check` exits 0: every generated block matches current `eval/results` (no stale numbers).
- `report.md` has headings a–d, a "Failure analysis" section with ≥2 cases, and a "Trade-offs" section.
- `architecture.dot` names every pipeline stage listed in SPEC §2.

## Limits and out of scope
- PDF and PNG are committed build outputs; CI checks sources and tables, not the PDF rendering.
- Live Claude demo (`curl /chat` with benign / injection / PII / crisis): I run it once with your `.env` and paste the
  reports into the README; CI stays on MockLLM.
- `chore/plugin` and further `fix/*` branches come after this PR.
