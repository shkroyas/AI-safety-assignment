# How this project uses Claude Code

The guardrails were built with Claude Code. This page lists each feature, where it lives,
and a log of how it was actually used. Entries are added as the work happens, not afterwards.

## Features

| Feature | Where | What it does here |
|---|---|---|
| CLAUDE.md | `CLAUDE.md` | Commands, layout, rules and git policy loaded into every session |
| Spec-driven development | `SPEC.md`, `docs/specs/` | Spec approved before code; each branch adds a spec delta, then failing tests, then code |
| Hooks | `.claude/settings.json`, `.claude/hooks/` | `guard_bash.py` (PreToolUse) blocks push to main, force-push, commit-date overrides and staging `.env`. `format_python.py` (PostToolUse) runs ruff on edited `.py` files. `stop_tests.py` (Stop) runs the fast tests before a turn ends |
| Skills | `.claude/skills/` | `start-feature`, `add-test-case`, `run-eval`, `nepal-recognizer` |
| Subagents | `.claude/agents/` | `red-teamer`, `guardrail-reviewer` (read-only), `eval-analyst` |
| MCP | `.mcp.json`, `src/guardbank/mcp_server.py` | Exposes the guardrails as tools (`check_input`, `check_output`, `run_case`). Added in `feat/api-mcp` |
| Plugin | `plugins/guardbank-dev/`, `.claude-plugin/marketplace.json` | Packages the 4 skills, 3 agents and 3 hooks for reuse (e.g. a fresh clone or another worktree). Generated from `.claude/` by `scripts/sync_plugin.py`; a test fails on drift. Added in `chore/plugin` |
| Permissions | `.claude/settings.json` | Allow-list for test/lint commands; deny reads of `.env`, model caches, logs and eval JSONL |

## Context window management

- **Spec as the anchor.** SPEC.md and CLAUDE.md carry the decisions, so a session can be
  cleared without losing them.
- **`/clear` between branches.** Each feature branch starts in a fresh context with only
  CLAUDE.md, the spec section and the branch's spec delta.
- **`/compact` with a focus note** inside long branches, e.g.
  `/compact keep the injection regex decisions and failing test ids`.
- **Subagents for wide reads.** Explore and the `eval-analyst`/`red-teamer` agents read
  many files or long outputs in their own context and return only the conclusion.
- **Deny rules** keep large or sensitive files out of context: labeled eval sets, model
  caches, logs, `.env`.
- **Skills load on demand.** Only their one-line descriptions sit in context until one is used.

## Usage log

| Date | Branch | What happened |
|---|---|---|
| 2026-11-19 | — | Plan mode: read the assignment PDF and implementation-plan PDF, asked about LLM backend, scope, merge policy and deadline, then wrote and got approval for a plan |
| 2026-11-19 | `main` | SPEC.md v2 approved (adds Claude API + MockLLM, Claude Code layer, git workflow). First commit |
| 2026-11-19 | `chore/claude-code-setup` | Wrote `tests/hooks/test_guard_bash.py` first. The run exposed false passes (a missing script also exits 2), so the block tests only count once the hook exists. Then wrote the hook: 22/22 pass |
| 2026-11-19 | `main`, `chore/claude-code-setup` | Royas asked to be sole author. With explicit one-time approval, `git filter-branch --msg-filter` removed the co-author trailer from the 7 pushed commits (author/committer dates unchanged), force-pushed once, then branch protection was turned on for `main` |
| 2026-11-19 | `chore/claude-code-setup` | Side effect of the rewrite: replacing `main`'s root left PR #1 with no shared history, so GitHub auto-closed it and refused to reopen. Opened PR #2 from the same branch. Lesson: rewrite the head branch before the base, or avoid rewriting a PR's base at all |
| 2026-11-19 | `feat/skeleton` | Loaded the `claude-api` skill and read the current Bedrock docs before writing the client. Found that Opus 4.6 is only on Bedrock's `bedrock-runtime` path and that SDK 2.x sends an API version it rejects, so the spec delta pinned `anthropic[bedrock]<2`. Spec delta approved, then failing tests committed before code |
| 2026-11-19 | `feat/skeleton` | Live run on Bedrock: valid `SupportReply` JSON in 3.5 s. Found a retrieval miss to carry into the eval: for "ATM limit and annual card fee", top-4 (hashing embedder) missed `atm-cards#3`; the model correctly declined the fee part instead of inventing it |
| 2026-11-19 | `chore/token-optimisation` | Measured context costs: CLAUDE.md ~650 tok/turn; the session's big costs were one-off reads (2 PDFs as images, the claude-api skill, 2 full Bedrock doc pages ≈30k tok). Added one-feature-per-branch roadmap, `start-feature` skill, `spec_section.sh`, ≤40-line spec template, quieter pytest/Stop-hook output and a Bash output cap |
| 2026-11-27 | `chore/plugin` | `claude plugin validate --strict` passed for the plugin and the marketplace. Installed it with `CLAUDE_CONFIG_DIR` pointed at a scratch directory, so the real config was untouched: `plugin details` listed 4 skills, 3 agents, 3 hooks, ~376 always-on tokens. The validator's catalog checks flag a missing LICENSE and icon; not needed for a local marketplace |
| 2026-11-27 | `fix/injection-pii-refusals` | Measured before writing the spec: DeBERTa refused 15/47 benign PII messages, unseen by the eval. Prompt Guard 2 401s had two causes found in turn: a fine-grained HF token without gated-repo read, then `load_dotenv()` in a scratch script searching from the script's folder, not the repo. The first approved fix (Prompt Guard 2 for PII messages) failed its own acceptance rule on the new `injection_pii` set (attack recall 2/4 dev), so the spec was amended to the both-must-flag rule instead of shipping it |
| 2026-11-27 | `fix/crisis-recall` | Measured P(CRISIS) on every topic item before the spec: TOPE-007 was ranked CRISIS (0.547) and lost only to the shared τ 0.7. Because its score was seen when choosing 0.5, a held-out `crisis` set was written after the threshold was fixed, and the report states the bias |
| 2026-11-27 | `fix/injection-lookalikes` | Measured candidate regexes on every set that uses them before the spec, including the chunk scan (which reuses the patterns): the first draft dropped poisoned chunk POIS-010 ("developer mode enabled"), caught before any code was written. Checked that DeBERTa still blocks the role overrides the narrower regex lets through |
| 2026-11-27 | `fix/output-overredaction` | Rebuilt the live reply and ran it through the real leakage check: the PASSWORD cause reproduced, the hotline cause did not (the corpus spelling is kept). Tested Unicode-hyphen and markdown variants, then stopped and wrote the unconfirmed part into the spec rather than guessing further; `logs/` stayed unread per the deny rule. The new `leakage_pii` set showed the digit rule had no measured effect, and the report says so |
| 2026-11-27 | `fix/landline-pii` | Used the `nepal-recognizer` skill, adapted to the current `_PATTERNS` code. Measuring the three leaks missed in #26 showed two were mislabeled (a wrong toll-free hotline is not personal data, and groundedness already catches it), so the spec corrected the labels instead of widening the PII rules |
| 2026-11-27 | `fix/encoded-payloads` | Took an external review file as input: reproduced each claim before acting, ranked by reproduced severity, and noted the overstated ones (an unreachable branch, an OOM not seen here). Measured the wider decoder on all 656 benign texts before the spec. The eval's `dirty=True` stamp exposed untracked spec files for later branches; moved them aside and re-ran so results are stamped clean |
| 2026-11-27 | `fix/claim-splitting` | A slow leakage test failed after the change. Traced it rather than adjusting the test: the leakage check reuses the splitter, and a clean corpus line had only passed because of its "- " prefix. Measured all 369 clean sentences against the leak items, then asked Royas before moving the threshold (0.75 → 0.78) and amended the spec |
| 2026-11-27 | `fix/prompt-leak-fp` | The first fix let the slow test progress to a second, hidden failure on the same reply (GLiNER tagging "human"). Measured the neighbouring nouns before extending the list, kept real names covered, and recorded the scope addition as a spec amendment |

## Installing the plugin

```bash
/plugin marketplace add ./            # from the repo root; the marketplace is named guardbank
/plugin install guardbank-dev@guardbank
```

Skills and agents then appear namespaced (`guardbank-dev:run-eval`). Do not enable the plugin in
a checkout that also has `.claude/settings.json` hooks active, or every hook runs twice. The MCP
server is not bundled: it needs this repo's code and stays in the root `.mcp.json`. Permissions
and env from `settings.json` are not bundled either (plugins cannot set them). After changing
anything under `.claude/skills`, `.claude/agents` or `.claude/hooks`, run
`python scripts/sync_plugin.py`.

## Context per branch

Context size at PR time, from `/context` (filled in from `feat/input-normalizer` on).

| Branch | Context at PR | Notes |
|---|---|---|
| `feat/input-pii` (#6) | 101.5k / 1m (10%) | Messages 66.7k, system tools 14.8k, skills 9.9k (148, mostly unrelated plugins), memory 1.5k. 454 MCP tools stay deferred (~299k if all loaded, Higgsfield alone ~150k), so they cost nothing until searched. Biggest message costs: `uv add` output and the spec rewrite to fit 40 lines |
