# Spec delta: feat/ml-output (step 10b of feat/ml-detectors)

SPEC section: 4. Output guardrails (Groundedness: HHEM-2.1-open; Sensitive info: embedding similarity). ≤40 lines.

## Scope
- `output/hhem.py`: `HHEMScorer` (`ClaimScorer`), a vendored copy of HHEM-2.1-open's 20-line wrapper (Apache-2.0, attributed):
  plain `T5ForTokenClassification` on `google/flan-t5-base` + `model.safetensors` of `vectara/hallucination_evaluation_model`
  pinned to revision `de9a5e6…`. No `trust_remote_code`. Encoder embedding tied to `shared` explicitly. Lazy load, cached.
- `ClaimScorer.score(claim, evidences: list[str])`: full claim text, one string per cited chunk. Keyword joins them and blanks
  numbers/dates itself (helpers move to `output/facts.py`); HHEM returns the max consistency probability over chunks.
- Leakage gets its own embedder (`hashing` | `sentence-transformers`) and drops `public_prompt_lines`: prompt sentences that only
  restate published policy (PIN rule, advice rule, bank identity), which clean corpus text legitimately matches.

## Behaviour
- `output.groundedness.scorer: keyword|hhem`; HHEM has its own `tau_g` (0.5) that overrides the keyword one. Unknown → `ValueError`.
- HHEM prompts over `max_length` (512) tokens are truncated; claims spanning two chunks can score low (multi-hop limit).
- Measured on "limit NPR 25,000; other ATM costs NPR 25": restatement 0.94, wrong amount 0.16, invented 0.003,
  paraphrase 0.89, negation 0.02 (the keyword baseline misses the last two).
- Leakage `tau_prompt` per embedder. Measured with public lines dropped (clean corpus max | verbatim, summary, paraphrase, JSON leaks):
  hashing 0.23 | 1.0, 0.43, 0.13, 0.73 → `0.40`; bge-small 0.72 | 1.0, 0.78, 0.69, 0.91 → `0.75`. Both miss the paraphrase.

## Config (`config/guardrails.yaml`)
```yaml
output:
  groundedness: {scorer: keyword, hhem: {name: vectara/hallucination_evaluation_model, revision: de9a5e6…, foundation: google/flan-t5-base,
                 prompt: "<pad> Determine if the hypothesis is true given the premise?…", max_length: 512, tau_g: 0.5, device: auto}}
  leakage: {embedder: hashing, embedding_model: BAAI/bge-small-en-v1.5, tau_prompt: {hashing: 0.40, sentence-transformers: 0.75},
            public_prompt_lines: ["PINs, passwords", "investment, tax or legal advice", "a fictional bank in Nepal"]}
```

## Tests first
- Fast: keyword scorer on a list of evidences; existing groundedness tests unchanged in outcome; HHEM factory is lazy;
  unknown scorer raises; HHEM tau overrides; public prompt lines excluded; leakage tau per embedder; summary leak now blocked.
- Slow (`tests/output/test_ml_output.py`): HHEM score table above (thresholds 0.8 / 0.5 / 0.1); embedding tied; groundedness
  with HHEM allows the paraphrase and flags the negation; bge-small leakage blocks verbatim/summary/JSON, flags no clean sentence.

## Out of scope
- Tuning tau_g / tau_prompt on dev and the keyword vs NLI vs NLI+number ablation: `feat/eval`.
