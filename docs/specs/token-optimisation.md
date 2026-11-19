# Spec delta: chore/token-optimisation

Goal: every remaining branch is **one feature**, starts from a clean context, and reads only
what it needs. Measured baseline (chars/4): CLAUDE.md 650 tok/turn, SPEC.md 1.9k, corpus 6k,
src 5.3k. This session's biggest costs were one-off reads in the main context: 2 PDFs as
images, the full claude-api skill, and 2 whole Bedrock doc pages (~30k tok together).

## 1. One feature per branch (`docs/roadmap.md`)
Remaining work split into 14 small branches, each with one spec delta, one PR, about 200–600 lines:
1 `feat/input-normalizer` · 2 `feat/input-pii` · 3 `feat/input-injection` · 4 `feat/input-topics`
· 5 `feat/chunk-scan` · 6 `feat/output-schema` · 7 `feat/output-groundedness`
· 8 `feat/output-leakage` · 9 `feat/remediation-pipeline` · 10 `feat/ml-detectors`
· 11 `feat/e2e-cases` · 12 `feat/eval` · 13 `feat/api-mcp` · 14 `docs/report` (+ `fix/*` from eval, `chore/plugin`).

## 2. `start-feature` skill
One command per branch: sync `main`, create the branch, copy the spec-delta template, and print
only the SPEC section that branch needs (`scripts/spec_section.sh <heading>`), plus the files to
touch. No exploratory reads.

## 3. Spec-delta template (`docs/specs/_template.md`)
At most ~40 lines: scope, behaviour, config keys, tests first, out of scope.

## 4. Token rules in CLAUDE.md (kept short)
- `/clear` at every branch start; `/compact <focus>` at milestones; check `/context` when long.
- Read file ranges or grep; never read `data/corpus/` or eval sets whole.
- Web pages and long docs go through the `web-fetch` / Explore subagents with one focused
  question; only the answer enters the main context.
- Subagents run on Sonnet; the main session keeps the reasoning.

## 5. Quieter tool output
- pytest `addopts = "-q --tb=short --no-header"`; the Stop hook prints only failing test lines.
- `.claude/settings.json` env `BASH_MAX_OUTPUT_LENGTH=20000` caps runaway command output.

## 6. Measurement
The usage log gets a column per branch: context tokens at PR time from `/context`, so the
effect is measured rather than claimed.

Out of scope: the app's own Claude calls. The system prompt is ~1k tokens, mostly retrieved
context that changes per question, and Opus 4.6 on Bedrock's legacy path needs explicit cache
breakpoints, so prompt caching would save little. Revisit if the static prompt grows.
