#!/usr/bin/env bash
# UserPromptSubmit hook: keeps the unslop writing rules in context on every turn, so they
# survive context compaction. The full text is the `unslop` skill of this plugin.
# Disable for one session with UNSLOP_HOOK=0.

# Drain the hook payload so the caller never sees a broken pipe.
cat >/dev/null 2>&1 || true

if [ "${UNSLOP_HOOK:-1}" = "0" ]; then
  exit 0
fi

cat <<'REMINDER'
<unslop-reminder>
Writing rules in force (skill `unslop`). They cover every reply, commit message, PR or issue
body, doc, code comment and subagent brief. They never cover code identifiers, quoted user or
UI text, cited sources, or prose you were not asked to edit.

Fast pass:
- No em dashes. Use a period or a comma. Parentheses and en dashes are not legal swaps.
- No opening sycophancy ("Great question!"), no closing "Let me know if...".
- Delete "It is important to note that". "In order to" becomes "To".
- No bold-label-colon bullets that restate the line.
- Cut any sentence that would fit another project's docs unchanged.
- Sentence case headings, straight quotes, no decorative emoji.

Read the full skill before any substantial piece of writing.
</unslop-reminder>
REMINDER

exit 0
