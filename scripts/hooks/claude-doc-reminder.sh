#!/usr/bin/env bash
# Claude Code PostToolUse hook — reminds the agent to update docs when
# user-visible source changes. Opt-in via .claude/settings.local.json.
#
# Input: JSON on stdin with at least `.tool_input.file_path`.
# Output: JSON on stdout with a `systemMessage` that Claude sees as
# additional context before its next turn.
#
# The reminder fires only for paths under core/ or web/src/ — build
# artefacts, tests, hooks, and docs themselves are ignored.

set -euo pipefail

input=$(cat || true)
if [[ -z "$input" ]]; then
  exit 0
fi

path=$(printf '%s' "$input" | python -c 'import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass' 2>/dev/null || true)

if [[ -z "$path" ]]; then
  exit 0
fi

case "$path" in
  */core/*|*\\core\\*|*/web/src/*|*\\web\\src\\*)
    cat <<'EOF'
{
  "systemMessage": "Doku-Check: user-visible Source wurde geaendert. Vor dem Commit pruefen: CHANGELOG.md-Eintrag bei feat/fix, ROADMAP.md bei neuem Meilenstein-Feature, README.md bei Status-Aenderung. Der pre-commit hook blockiert feat/fix-Commits ohne CHANGELOG-Eintrag."
}
EOF
    ;;
esac

exit 0
