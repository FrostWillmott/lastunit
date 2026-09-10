#!/bin/bash
# PostToolUse hook: lint the just-edited file. Advisory only — never blocks
# the session, even if jq/uv/npm are missing or the project has no env yet.
command -v jq >/dev/null || exit 0

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -n "$FILE" ]] || exit 0

case "$FILE" in
  *.py)
    command -v uv >/dev/null || exit 0
    uv run ruff check --fix "$FILE" 2>&1 | head -10
    ;;
  */frontend/*.ts|*/frontend/*.tsx|*/frontend/*.js|*/frontend/*.jsx|*/frontend/*.vue)
    # Frontend lint runs only if deps are installed; otherwise stay silent.
    ROOT="${FILE%%/frontend/*}/frontend"
    [[ -d "$ROOT/node_modules" ]] || exit 0
    (cd "$ROOT" && npx --no-install eslint "$FILE" 2>&1 | head -10)
    (cd "$ROOT" && npx --no-install prettier --write "$FILE" >/dev/null 2>&1)
    ;;
esac

exit 0
