---
name: start-feature
description: Start the next single-feature branch from docs/roadmap.md with minimal context: sync main, create the branch, draft the spec delta from the template, and read only the needed SPEC section. Use at the start of every new feature branch.
---

# Start a feature branch (token-lean)

Assumes a fresh context (`/clear` after the previous PR merged).

1. Find the branch: the argument, or the first row of `docs/roadmap.md` with empty Status.
2. `git switch main && git pull --ff-only`, then `git switch -c <branch>`.
3. Read only what the branch needs:
   - `scripts/spec_section.sh "<Spec column heading>"` (not the whole SPEC.md)
   - the module(s) it extends: grep for names first, then read line ranges
   - never read `data/corpus/` or `data/eval/` whole; grep them
4. Copy `docs/specs/_template.md` to `docs/specs/<feature>.md` and fill it in (≤40 lines).
5. Stop and ask Royas to approve the spec delta. Code starts only after the OK.

For anything on the web or a long document, use a `web-fetch` or Explore subagent with one
focused question instead of reading it in the main context.
