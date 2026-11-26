# Spec delta: chore/plugin

SPEC section: 9. Claude Code development layer (Plugin row). No guardrail code changes. ≤40 lines.

## Scope
- `plugins/guardbank-dev/`: a Claude Code plugin bundling the 4 skills (add-test-case, run-eval,
  nepal-recognizer, start-feature), 3 agents (red-teamer, guardrail-reviewer, eval-analyst) and the 3 hooks.
- `.claude-plugin/marketplace.json` at the repo root, so `/plugin marketplace add ./` then
  `/plugin install guardbank-dev@guardbank` installs it (e.g. in a fresh clone or a worktree).

## Behaviour
- Single source stays `.claude/`. The project keeps working exactly as now (no namespaced skill names,
  no double hooks). `scripts/sync_plugin.py` copies skills, agents and hook scripts into the plugin;
  `--check` exits 1 on any drift.
- `plugins/guardbank-dev/.claude-plugin/plugin.json`: name `guardbank-dev`, version `0.1.0`, description,
  author Royas Shakya. `hooks/hooks.json` mirrors `.claude/settings.json` hooks with
  `${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py` instead of `$CLAUDE_PROJECT_DIR/.claude/hooks/`.
- Hook scripts still act on the project they run in (they already use the project dir / cwd).
- Not bundled: the MCP server (it needs this repo's code and stays in the root `.mcp.json`), permissions
  and env from `settings.json` (plugins cannot set them).
- Docs: README "How it was built" and `docs/claude-code-workflow.md` get install steps and a warning:
  do not enable the plugin in this repo itself, or hooks run twice.

## Config
- None.

## Tests first (`tests/test_plugin.py`, fast)
- `sync_plugin.py --check` exits 0 (plugin copies equal `.claude/` sources).
- plugin.json and marketplace.json parse; the marketplace entry's name/source point at the plugin
  directory and its version matches plugin.json.
- `hooks/hooks.json` has the same events and matchers as `.claude/settings.json`, every command uses
  `${CLAUDE_PLUGIN_ROOT}`, and every referenced script exists.
- `claude plugin validate` passes on the plugin and the marketplace (skipped when `claude` is not on PATH,
  so CI skips it; run locally before the PR).

## Limits and out of scope
- Copies, not symlinks: plugin installs copy the directory, and symlinks break on Windows.
- No plugin eval suite (`claude plugin eval`); out of scope.
