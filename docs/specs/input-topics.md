# Spec delta: feat/input-topics

SPEC section: 3. Input guardrails (Sensitive topic row + routing table) + 2. Pipeline order (step 4). ≤40 lines.

## Scope
- `input/topics.py`: `TopicRouter.check(text) -> GuardResult` (stage `"input_topic"`): crisis fast-path, then
  keyword rules per category, then a classifier hook. A YAML routing table sets action and reply.
- `TopicClassifier` protocol (`predict(text) -> (label, prob)`) in `input/detectors.py`; CPU stub → `("NORMAL", 0.0)`.

## Behaviour
- Categories (YAML order = priority): `CRISIS`, `FRAUD_INTENT`, `SCAM_VICTIM`, `COMPLAINT`, `ADVICE`, `OFF_TOPIC`, else `NORMAL`.
- Crisis fast-path on normalized text ("end it (all)", "end my life", "kill myself", "suicid*", "want to die",
  "no reason to live", "harm myself"): hit returns at once with score 1.0; the classifier is not called.
- Else the first keyword category hit (score 1.0); else the classifier label if `prob >= tau`; else `NORMAL`.
- Routing → `action`, `details.route`, `details.escalate`, optional `details.response` / `details.disclaimer`:
  | Category | action | route | escalate | extra |
  |---|---|---|---|---|
  | CRISIS | ROUTE | `crisis` | true | `response`: empathy + helpline 1166 + offer human agent; no refusal wording |
  | FRAUD_INTENT | BLOCK | `block` | false | `response`: generic refusal |
  | SCAM_VICTIM / COMPLAINT | ROUTE | `answer` | true | answered from corpus (card-block steps / grievance process) |
  | ADVICE | ROUTE | `answer` | false | `disclaimer`: general info only, no personal recommendation |
  | OFF_TOPIC | ROUTE | `redirect` | false | `response`: polite redirect to banking scope |
  | NORMAL | ALLOW | `answer` | false | — |
- `detected = category != NORMAL`; `details.matches` = rule names hit; `details.source` = `crisis|keyword|classifier`.
- Benign look-alikes stay NORMAL: "I'm dying to know the FD rate", "how do I end my standing order?", "kill the app session".

## Config (`config/guardrails.yaml`, under `input.topics`)
- `classifier: stub` (stub | embed_logreg in feat/ml-detectors), `tau: 0.7`, `crisis: [regex…]`, `categories: {NAME: [regex…]}`.
- `helpline: {name: National Suicide Prevention Helpline, number: "1166", source: <WHO SEARO feature-story URL>}`.
- `routes: {CATEGORY: {action, route, escalate, response?, disclaimer?}}`; `{helpline_number}` filled into the crisis text.

## Tests first (`tests/input/test_topics.py`, all fast)
- `test_routing_table` (parametrized: each SPEC example → category, action, route, escalate),
  `test_crisis_fast_path_skips_classifier`, `test_crisis_reply_has_helpline_and_human_offer`, `test_crisis_never_cold_refusal`,
  `test_benign_lookalikes_normal`, `test_classifier_over_tau_used`, `test_classifier_under_tau_normal`, `test_keyword_beats_classifier`.

## Limits and out of scope
- Romanized Nepali crisis phrases, sarcasm, fuzzy category edges: documented; left to the classifier and eval.
- Helpline hours are unconfirmed, so the reply states none. Real classifier → `feat/ml-detectors`; wiring → `feat/remediation-pipeline`.
