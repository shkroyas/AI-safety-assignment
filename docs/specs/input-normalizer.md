# Spec delta: feat/input-normalizer

SPEC section: 2. Pipeline order (step 1). One feature only; ≤40 lines.

## Scope
- `src/guardbank/input/normalizer.py`: `Normalizer.check(text) -> GuardResult` (stage `"normalizer"`).
- Produces the canonical text every later input detector scans, plus any decoded payloads.

## Behaviour
- Order: NFKC → strip zero-width/bidi controls (U+200B–U+200F, U+202A–U+202E, U+2060–U+2064, U+FEFF)
  → map homoglyphs (Cyrillic/Greek look-alikes → Latin, from a table in YAML) → collapse whitespace.
- Decode: tokens matching base64 (len ≥ `min_len`, valid padding, decodes to ≥ `min_printable` printable
  UTF-8) or hex (even length ≥ `min_len`, `0x` optional) are decoded once (no recursion).
- Output: `details.normalized` (str), `details.decoded` (list[str]), `details.changes` (list of
  `"nfkc" | "zero_width" | "homoglyph" | "base64" | "hex"`). Spans mark each changed/decoded region
  of the original text with label = change type.
- `detected = bool(changes)`, `score = 1.0` if a decode or homoglyph fired else `0.5` if only
  NFKC/zero-width else `0.0`. Action is always `ALLOW`: the normalizer never blocks; later stages
  scan `normalized` and each `decoded` string.
- Plain ASCII banking text passes through unchanged (`detected=False`).

## Config (`config/guardrails.yaml`)
```yaml
input:
  normalizer:
    decode: {min_len: 16, min_printable: 0.9}
    homoglyphs: {"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "і": "i", "ο": "o", ...}
```

## Tests first (`tests/input/test_normalizer.py`, fast)
- `test_plain_text_unchanged`, `test_nfkc_fullwidth`, `test_strips_zero_width`,
  `test_homoglyph_ignore` ("іgnоrе" → "ignore"), `test_base64_decoded`, `test_hex_decoded`,
  `test_short_or_binary_not_decoded` (account numbers / random tokens stay), `test_spans_point_to_original`,
  `test_returns_guardresult_allow`, `test_config_drives_thresholds`.

## Limits and out of scope
- No recursive/nested decoding, ROT13, leetspeak or URL-encoding (note in report).
- Homoglyph mapping may alter legitimate Nepali-in-Latin or Cyrillic text; Devanagari is untouched.
- Wiring into the pipeline is `feat/remediation-pipeline`.
