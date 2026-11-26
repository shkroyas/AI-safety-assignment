---
name: nepal-recognizer
description: Add or change a Presidio recognizer for a Nepal-specific PII format (citizenship number, PAN, +977 mobile, bank account number, etc.). Use when a PII format is missed or over-detected.
---

# Add a Nepal PII recognizer

1. Write the format down first in `docs/specs/pii.md`: entity name, regex, context words,
   base score, and 3 valid + 3 look-alike negative examples (order ids, dates, amounts).
2. Add failing tests in `tests/input/test_pii.py`: each positive must be found with the right
   entity type and span; each negative must not be.
3. Implement as a `PatternRecognizer` in `src/guardbank/input/pii.py`, with context words
   to raise the score. Register it in the analyzer factory. Put the score threshold in
   `config/guardrails.yaml`, not in code.
4. Run `uv run pytest -q tests/input/test_pii.py`, then the PII slice of the eval
   (`/run-eval`) to check precision didn't drop.
5. Note new limitations (e.g. Devanagari digits) in the spec's PII "Known limits" column.
