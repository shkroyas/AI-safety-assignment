#!/usr/bin/env bash
# Print one "## <heading>" section of a spec (default SPEC.md), including its ### subsections,
# so a branch reads only the part of the spec it needs.
# Usage: scripts/spec_section.sh "3. Input guardrails" [file]
set -euo pipefail
heading="$1"
file="${2:-SPEC.md}"
out=$(awk -v h="## $heading" '
  $0 == h { on = 1; print; next }
  on && /^## / { exit }
  on { print }
' "$file")
if [ -z "$out" ]; then
  echo "section '## $heading' not found in $file" >&2
  exit 1
fi
printf '%s\n' "$out"
