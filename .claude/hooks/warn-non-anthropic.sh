#!/bin/bash
# SessionStart hook: flag when a non-Anthropic endpoint is active, so an
# audit/dual-review session doesn't silently run generator and auditor on the
# same underlying model.
if [[ -n "${ANTHROPIC_BASE_URL:-}" ]]; then
  echo "WARNING: non-Anthropic endpoint active ($ANTHROPIC_BASE_URL). Do not run audits in this session."
fi

exit 0
