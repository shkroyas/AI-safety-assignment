# Roadmap: one feature per branch

Each branch: `/start-feature <branch>` → spec delta (≤40 lines, approved) → failing tests →
code → PR with green CI → Royas merges → `/clear`. "Spec" = the SPEC.md section to read.

| # | Branch | Feature | Spec | Status |
|---|---|---|---|---|
| 0 | `chore/claude-code-setup` | CLAUDE.md, hooks, skills, subagents | 9. Claude Code development layer | merged #2 |
| 0 | `feat/skeleton` | types, audit, corpus, retriever, LLM, CI | 2. Pipeline order | merged #3 |
| 0 | `chore/token-optimisation` | roadmap, start-feature skill, token rules | 10. Git workflow | merged #4 |
| 1 | `feat/input-normalizer` | NFKC, zero-width, homoglyphs, base64/hex decode | 2. Pipeline order | merged #5 |
| 2 | `feat/input-pii` | Presidio + Nepal recognizers, typed-token vault | 3. Input guardrails | merged #6 |
| 3 | `feat/input-injection` | regex bank + canary-aware refusal | 3. Input guardrails | merged #7 |
| 4 | `feat/input-topics` | crisis fast-path + routing table (verified helpline) | 3. Input guardrails | merged #8 |
| 5 | `feat/chunk-scan` | injection scan on retrieved chunks, drop poisoned | 2. Pipeline order | merged #9 |
| 6 | `feat/output-schema` | SupportReply + citation-exists + fault injection | 4. Output guardrails | merged #10 |
| 7 | `feat/output-groundedness` | claim split, number/date match, keyword baseline | 4. Output guardrails | merged #11 |
| 8 | `feat/output-leakage` | output PII diff, canary, prompt similarity | 4. Output guardrails | merged #12 |
| 9 | `feat/remediation-pipeline` | remediation policy + full pipeline + audit per stage | 4. Output guardrails | merged #13 |
| 10a | `feat/ml-input` | DeBERTa / Prompt Guard 2, GLiNER, topic classifier | 3. Input guardrails | merged #14 |
| 10b | `feat/ml-output` | HHEM groundedness, sentence-transformer prompt similarity | 4. Output guardrails | this PR |
| 11 | `feat/e2e-cases` | 40+ cases in `tests/cases.yaml` | 5. Test case format | |
| 12 | `feat/eval` | labeled sets, metrics, ablations, sweeps, latency | 6. Evaluation | |
| 13 | `feat/api-mcp` | FastAPI `/chat` + MCP server | 9. Claude Code development layer | |
| 14 | `docs/report` | architecture diagram, README, report | — | |
| — | `fix/*` | one per real failure found by the eval | 6. Evaluation | |
| — | `chore/plugin` | package skills/agents/hooks as a plugin | 9. Claude Code development layer | |
