# How this project uses Claude Code

The guardrails were built with Claude Code. This page lists each feature, where it lives,
and a log of how it was actually used. Entries are added as the work happens, not afterwards.

## Features

| Feature | Where | What it does here |
|---|---|---|
| CLAUDE.md | `CLAUDE.md` | Commands, layout, rules and git policy loaded into every session |
| Spec-driven development | `SPEC.md`, `docs/specs/` | Spec approved before code; each branch adds a spec delta, then failing tests, then code |
| Hooks | `.claude/settings.json`, `.claude/hooks/` | `guard_bash.py` (PreToolUse) blocks push to main, force-push, commit-date overrides and staging `.env`. `format_python.py` (PostToolUse) runs ruff on edited `.py` files. `stop_tests.py` (Stop) runs the fast tests before a turn ends |
| Skills | `.claude/skills/` | `add-test-case`, `run-eval`, `nepal-recognizer` |
| Subagents | `.claude/agents/` | `red-teamer`, `guardrail-reviewer` (read-only), `eval-analyst` |
| MCP | `.mcp.json`, `src/guardbank/mcp_server.py` | Exposes the guardrails as tools (`check_input`, `check_output`, `run_case`). Added in `feat/api-mcp` |
| Plugin | `plugins/guardbank-dev/`, `.claude-plugin/marketplace.json` | Packages the skills, agents and hooks for reuse. Added in `chore/plugin` |
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

