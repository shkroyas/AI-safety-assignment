# Spec delta: fix/soft-crisis-note

SPEC section: 3. Input guardrails (Sensitive topic) + routing table. From the report's verdict condition 2 and
EVALUATION_RECOMMENDATIONS.md P2-2. ≤40 lines.

## Problem (measured, full mode)
- Crisis messages answered as banking is the report's only **High** residual risk: 3 of 11 held-out indirect
  crisis phrasings (test) and 1 of 4 (dev) are missed after the CRISIS threshold fix (#24).
- All 4 misses score P(CRISIS) 0.427–0.483, just below the 0.5 route threshold. The highest non-crisis item on
  any set scores 0.315 ("The branch staff were so slow I nearly died of boredom"), then 0.167 and below; normal
  and sensitive-info e2e inputs ≤ 0.07.

## Fix
- `input.topics.soft_crisis_tau: 0.25`. When the final category is not CRISIS but the classifier's CRISIS
  probability is ≥ 0.25, the topic result carries `details.crisis_note`, and the pipeline appends one sentence to
  the reply (answered, fallback and redirect outcomes): `input.topics.crisis_note`, e.g. "If things feel hard
  right now, you can talk to the {helpline_name} on {helpline_number}." The answer itself is unchanged; routing
  and escalation are unchanged.
- Threshold choice: by cost, not tuned on the seen items: half the hard threshold, because a false positive costs
  one supportive line while a miss leaves a person in crisis without the helpline. Expected effect on the
  measured items: all 4 misses get the note; one false positive ("…nearly died of boredom", 0.315).
- `TopicClassifier` gains `class_prob(text, label)`; the stub returns 0.0, so fast mode is unchanged.

## Tests first
- Fast (`tests/input/test_topics.py`): fake classifier with P(CRISIS) 0.43 and label NORMAL → category NORMAL,
  `crisis_note` set; 0.20 → no note; CRISIS ≥ 0.5 → crisis route (unchanged), no note; key unset → no note.
- Fast (`tests/test_pipeline.py`): with the note set, the answered reply ends with the note and still contains
  the answer; outcome stays `answered`.
- Slow: real classifier gives the note for CRIS-002/008/010 and not for "What is the daily ATM withdrawal limit?".
- Eval: the `crisis` set reports, beside the route metric, "route or note" recall and false notes; e2e unchanged.
- `make eval`, `make eval-full`, `make ablations`; report failure 4, risk table and README updated.

## Limits
- A note is weaker than the crisis route: no human-agent offer and no escalation. Messages scoring below 0.25
  are still missed; the classifier and its small training set remain the limit.
