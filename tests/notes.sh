#!/usr/bin/env bash
# Tests for note.sh, the program note's log. Every note lives in a temp dir. Most tests pin the
# clock with NOTE_NOW, which exists for tests only.
#
#   tests/notes.sh            run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTE="$ROOT/plugins/flow/skills/long-haul/scripts/note.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
PASS=0
FAIL=0
unset NOTE_NOW NOTE_MAX_LINES

ok() { PASS=$((PASS + 1)); echo "  ok    $1"; }
no() { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/        /'; }
expect_code() { # name, wanted code, actual code, output
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (exit $3, wanted $2)" "$4"; fi
}
expect_has() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then ok "$1"; else no "$1 (missing: $2)" "$3"; fi
}
expect_not() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then no "$1 (found: $2)" "$3"; else ok "$1"; fi
}
expect_same() { # name, file, file
  if cmp -s "$2" "$3"; then ok "$1"; else no "$1 (files differ)" "$(diff "$2" "$3" | head -n 20)"; fi
}
expect_eq() { # name, wanted, actual
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (got '$3', wanted '$2')"; fi
}

STAMP_RE='^## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC$'
first_entry() { grep -nE '^## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC' "$1" | head -n 1 | cut -d: -f1; }
top_of() { awk -v n="$(( $(first_entry "$1") - 1 ))" 'NR > n { exit } { print }' "$1"; }
log_of() { tail -n +"$(first_entry "$1")" "$1"; }

# A top block with "## " headings that are not dated entries, then a two-entry log.
mknote() { # path
  cat >"$1" <<'EOF'
---
name: goal-demo
description: "RUNNING: demo"
---

STATUS: RUNNING

## Scope
Scope: epic #1, slices #2 to #4.

## 2026 plans, not an entry
## 2026-11-20 (draft), not an entry either

EOF
  printf '## 2026-11-20 08:00 UTC\n- Landed: #2\n- Next: #3\n\n## 2026-11-20 09:30 UTC\n- Running: backfill\n' >>"$1"
}
TOPLEN=13

echo "note.sh now and add"
out=$("$NOTE" now); rc=$?
expect_code "now succeeds" 0 "$rc" "$out"
if [[ "## $out" =~ $STAMP_RE ]]; then ok "now prints yyyy-mm-dd hh:mm UTC"; else no "now prints yyyy-mm-dd hh:mm UTC" "$out"; fi

D="$T/add"; mkdir -p "$D"; mknote "$D/goal-demo.md"
top_of "$D/goal-demo.md" >"$T/top.before"
out=$("$NOTE" add "$D/goal-demo.md" "Landed: #3"); rc=$?
expect_code "add one bullet" 0 "$rc" "$out"
head2=$(tail -n 2 "$D/goal-demo.md" | head -n 1)
if [[ "$head2" =~ $STAMP_RE ]]; then ok "the heading is stamped from the clock"; else no "the heading is stamped from the clock" "$head2"; fi
expect_eq "the bullet follows the heading" "- Landed: #3" "$(tail -n 1 "$D/goal-demo.md")"
expect_eq "a blank line comes before the heading" "" "$(tail -n 3 "$D/goal-demo.md" | head -n 1)"
expect_has "add reports what it wrote" "added 1 lines at" "$out"
expect_has "add reports the log size" "(log 9 lines)" "$out"

out=$(NOTE_NOW="2026-11-21 10:00 UTC" "$NOTE" add "$D/goal-demo.md" "Running: job A" "- Agents: one" "Next: merge"); rc=$?
expect_code "add several bullets" 0 "$rc" "$out"
printf '\n## 2026-11-21 10:00 UTC\n- Running: job A\n- Agents: one\n- Next: merge\n' >"$T/want"
tail -n 5 "$D/goal-demo.md" >"$T/got"
expect_same "several bullets in order, under one heading" "$T/want" "$T/got"
expect_not "a bullet that starts with '- ' is not prefixed twice" "- - Agents" "$(cat "$D/goal-demo.md")"
expect_has "add counts the bullets" "added 3 lines at 2026-11-21 10:00 UTC" "$out"

out=$(printf 'from stdin\n\n- second one\n   \nthird' | NOTE_NOW="2026-11-21 11:00 UTC" "$NOTE" add "$D/goal-demo.md" -); rc=$?
expect_code "stdin mode" 0 "$rc" "$out"
printf '## 2026-11-21 11:00 UTC\n- from stdin\n- second one\n- third\n' >"$T/want"
tail -n 4 "$D/goal-demo.md" >"$T/got"
expect_same "stdin gives one bullet per line and drops blank lines" "$T/want" "$T/got"

cp "$D/goal-demo.md" "$T/copy"
out=$("$NOTE" add "$D/goal-demo.md" "" "  " 2>&1); rc=$?
expect_code "only empty bullets is a usage error" 2 "$rc" "$out"
out=$(printf '\n\n' | "$NOTE" add "$D/goal-demo.md" - 2>&1); rc=$?
expect_code "empty stdin is a usage error" 2 "$rc" "$out"
out=$("$NOTE" add "$D/goal-demo.md" 2>&1); rc=$?
expect_code "add with no bullet at all is a usage error" 2 "$rc" "$out"
expect_same "the note is unchanged after the refused adds" "$T/copy" "$D/goal-demo.md"

out=$("$NOTE" add "$D/missing.md" "x" 2>&1); rc=$?
expect_code "a missing note file is a usage error" 2 "$rc" "$out"
[ -e "$D/missing.md" ] && no "the missing note was not created" || ok "the missing note was not created"

top_of "$D/goal-demo.md" >"$T/top.after"
expect_same "the top block is byte for byte the same after the adds" "$T/top.before" "$T/top.after"
expect_eq "the top block keeps its own ## headings" "$TOPLEN" "$(wc -l <"$T/top.after" | tr -d ' ')"
leftover=$(find "$D" -name '.*' -type f | wc -l | tr -d ' ')
expect_eq "no temp files are left next to the note" 0 "$leftover"

printf 'top line without a newline' >"$D/raw.md"
NOTE_NOW="2026-11-21 12:00 UTC" "$NOTE" add "$D/raw.md" "first" >/dev/null
printf 'top line without a newline\n\n## 2026-11-21 12:00 UTC\n- first\n' >"$T/want"
expect_same "a note without a final newline keeps its last line whole" "$T/want" "$D/raw.md"

mknote "$D/small.md"
out=$(NOTE_MAX_LINES=5 NOTE_NOW="2026-11-21 13:00 UTC" "$NOTE" add "$D/small.md" "a" 2>"$T/err"); rc=$?
expect_code "add over the limit still succeeds" 0 "$rc" "$out"
expect_has "over the limit it warns" "the log is 9 lines, over 5. Rotate it: note.sh rotate $D/small.md --summary" "$(cat "$T/err")"
out=$(NOTE_MAX_LINES=300 NOTE_NOW="2026-11-21 14:00 UTC" "$NOTE" add "$D/small.md" "b" 2>"$T/err"); rc=$?
expect_code "add under the limit succeeds" 0 "$rc" "$out"
expect_eq "under the limit it does not warn" "" "$(cat "$T/err")"

echo "note.sh check"
D="$T/check"; mkdir -p "$D"; mknote "$D/goal-demo.md"
out=$("$NOTE" check "$D/goal-demo.md"); rc=$?
expect_code "check on a note in order" 0 "$rc" "$out"
expect_has "check prints the log size" "log: 6 lines, limit 300" "$out"
expect_has "check prints the note size" "note: 1 KB" "$out"
expect_has "check prints first and last stamps" "first 2026-11-20 08:00 UTC, last 2026-11-20 09:30 UTC" "$out"
expect_has "check finds nothing out of order" "out of order: 0" "$out"

printf '\n## 2026-11-20 07:15 UTC\n- typed from memory\n\n## 2026-11-20 10:00 UTC\n- back on the clock\n' >>"$D/goal-demo.md"
out=$("$NOTE" check "$D/goal-demo.md"); rc=$?
expect_code "check fails on a stamp that goes backwards" 1 "$rc" "$out"
expect_has "it counts the backwards entry" "out of order: 1" "$out"
expect_has "it names the heading and its line" "line 21: ## 2026-11-20 07:15 UTC" "$out"

mknote "$D/long.md"
out=$(NOTE_MAX_LINES=3 "$NOTE" check "$D/long.md"); rc=$?
expect_code "check fails over the limit" 1 "$rc" "$out"
expect_has "it says the log is over" "OVER THE LIMIT" "$out"

printf 'just a top block\n## Not dated\n' >"$D/empty.md"
out=$("$NOTE" check "$D/empty.md"); rc=$?
expect_code "check on a note without a log" 0 "$rc" "$out"
expect_has "it says there is no log" "no log entries" "$out"

echo "note.sh rotate"
D="$T/rot"; mkdir -p "$D"; mknote "$D/goal-demo.md"
top_of "$D/goal-demo.md" >"$T/top.before"
log_of "$D/goal-demo.md" >"$T/log.before"
loglines=$(wc -l <"$T/log.before" | tr -d ' ')
out=$(NOTE_NOW="2026-11-22 12:00 UTC" "$NOTE" rotate "$D/goal-demo.md" --summary "Landed #2." --summary "Open: #3." --carry "backfill, log runs/b.log" 2>"$T/err"); rc=$?
R="$D/goal-demo-log-2026-11-22.md"
expect_code "rotate succeeds" 0 "$rc" "$out$(cat "$T/err")"
expect_has "it names the rotated file" "rotated $loglines log lines to $R" "$out"
expect_eq "the rotated file starts with its heading" "# goal-demo log, rotated 2026-11-22 12:00 UTC" "$(head -n 1 "$R")"
tail -n +3 "$R" >"$T/got"
expect_same "the rotated file holds every log line" "$T/log.before" "$T/got"
top_of "$D/goal-demo.md" >"$T/top.after"
expect_same "the main note keeps its top block byte for byte" "$T/top.before" "$T/top.after"
printf '## 2026-11-22 12:00 UTC\n- Rotated: %s log lines up to here moved to goal-demo-log-2026-11-22.md\n- Summary: Landed #2.\n- Summary: Open: #3.\n- Carried forward: backfill, log runs/b.log\n' "$loglines" >"$T/want"
log_of "$D/goal-demo.md" >"$T/got"
expect_same "the main note's log is one entry: Rotated, Summary, Carried forward" "$T/want" "$T/got"
expect_has "non-entry ## headings stay in the main note" "## 2026 plans, not an entry" "$(cat "$D/goal-demo.md")"
expect_not "non-entry ## headings are not moved" "## Scope" "$(cat "$R")"
expect_eq "with --carry there is no reminder" "" "$(cat "$T/err")"

out=$(NOTE_NOW="2026-11-22 12:30 UTC" "$NOTE" add "$D/goal-demo.md" "Landed: #3"); rc=$?
expect_code "add after rotate" 0 "$rc" "$out"
expect_has "add after rotate counts the new log" "(log 8 lines)" "$out"
out=$("$NOTE" check "$D/goal-demo.md"); rc=$?
expect_code "the note checks clean after rotate and add" 0 "$rc" "$out"
expect_has "two entries after rotate and add" "entries: 2" "$out"

out=$(NOTE_NOW="2026-11-22 13:00 UTC" "$NOTE" rotate "$D/goal-demo.md" --summary "Second rotation." 2>"$T/err"); rc=$?
expect_code "rotate again the same day" 0 "$rc" "$out"
[ -f "$D/goal-demo-log-2026-11-22-2.md" ] && ok "a taken name gets -2" || no "a taken name gets -2" "$(ls "$D")"
tail -n +3 "$R" >"$T/got"
expect_same "the first rotated file is untouched" "$T/log.before" "$T/got"
expect_has "without --carry it reminds on stderr" "Carry forward what is still live: running jobs, agents, holds, what the user owes" "$(cat "$T/err")"
leftover=$(find "$D" -name '.*' -type f | wc -l | tr -d ' ')
expect_eq "no temp files are left after rotate" 0 "$leftover"

mknote "$D/other.md"
cp "$D/other.md" "$T/copy"
out=$("$NOTE" rotate "$D/other.md" 2>&1); rc=$?
expect_code "rotate without --summary is a usage error" 2 "$rc" "$out"
out=$("$NOTE" rotate "$D/other.md" --summary 1 --summary 2 --summary 3 --summary 4 --summary 5 --summary 6 2>&1); rc=$?
expect_code "six summaries is a usage error" 2 "$rc" "$out"
out=$("$NOTE" rotate "$D/other.md" --summary 1 --bogus 2>&1); rc=$?
expect_code "an unknown rotate option is a usage error" 2 "$rc" "$out"
before=$(ls "$D" | wc -l | tr -d ' ')
out=$(NOTE_NOW="2026-11-22 14:00 UTC" "$NOTE" rotate "$D/other.md" --summary "s" --dry-run 2>&1); rc=$?
expect_code "rotate --dry-run succeeds" 0 "$rc" "$out"
expect_has "dry run names the target and the lines" "would move 6 log lines (lines 14 to 19) to $D/other-log-2026-11-22.md" "$out"
expect_same "dry run leaves the note as it was" "$T/copy" "$D/other.md"
expect_eq "dry run creates no file" "$before" "$(ls "$D" | wc -l | tr -d ' ')"

mkdir -p "$D/locked"; mknote "$D/locked/goal-x.md"; cp "$D/locked/goal-x.md" "$T/copy"
chmod a-w "$D/locked"
if [ -w "$D/locked" ]; then
  ok "a rotate that cannot write leaves the note (skipped: the directory stays writable for this user)"
else
  out=$(NOTE_NOW="2026-11-22 15:00 UTC" "$NOTE" rotate "$D/locked/goal-x.md" --summary "s" 2>&1); rc=$?
  expect_code "a rotate that cannot write its files fails" 1 "$rc" "$out"
  expect_same "the note is unchanged after the failed rotate" "$T/copy" "$D/locked/goal-x.md"
  expect_eq "the failed rotate leaves no file behind" 1 "$(ls -A "$D/locked" | wc -l | tr -d ' ')"
fi
chmod u+w "$D/locked"

out=$("$NOTE" rotate "$D/../check/empty.md" --summary "s"); rc=$?
expect_code "rotate on a note without a log" 0 "$rc" "$out"
expect_has "it says there is nothing to rotate" "nothing to rotate" "$out"

out=$("$NOTE" frobnicate 2>&1); rc=$?
expect_code "an unknown command is a usage error" 2 "$rc" "$out"
out=$(NOTE_MAX_LINES=lots "$NOTE" check "$D/other.md" 2>&1); rc=$?
expect_code "a non-numeric NOTE_MAX_LINES is a usage error" 2 "$rc" "$out"

echo "note.sh writers at once"
# Two adds at once used to lose an entry while both reported success.
R="$T/race"; mkdir -p "$R"
lost=0; failed=0
for round in 1 2 3 4 5; do
  printf 'top block\n' >"$R/n.md"
  pids=()
  for w in 1 2 3 4 5 6 7 8 9 10; do "$NOTE" add "$R/n.md" "writer $w round $round" >/dev/null 2>&1 & pids+=($!); done
  for p in "${pids[@]}"; do wait "$p" || failed=$((failed + 1)); done
  [ "$(grep -c '^- writer ' "$R/n.md")" -eq 10 ] || lost=$((lost + 1))
done
expect_eq "ten adds at once all land, five rounds" 0 "$lost"
expect_eq "and every one of them exits 0" 0 "$failed"
expect_eq "the top block is still the first line" "top block" "$(head -n 1 "$R/n.md")"
[ ! -e "$R/.n.md.lock" ] && ok "no lock is left behind" || no "no lock is left behind"

printf 'top block\n' >"$R/held.md"
echo $$ >"$R/.held.md.lock"                                  # held by a live process: this test
out=$(NOTE_LOCK_WAIT_S=1 "$NOTE" add "$R/held.md" "x" 2>&1); rc=$?
expect_code "a held lock makes add fail" 1 "$rc" "$out"
expect_has "it names the lock" "another writer holds" "$out"
expect_eq "the note is unchanged" "top block" "$(cat "$R/held.md")"
[ -f "$R/.held.md.lock" ] && ok "the other writer's lock is not removed" || no "the other writer's lock is not removed"
rm -f "$R/.held.md.lock"

printf 'top block\n' >"$R/stale.md"
( : ) & dead=$!; wait "$dead"                                # a pid that no longer runs
echo "$dead" >"$R/.stale.md.lock"
out=$("$NOTE" add "$R/stale.md" "after a killed run" 2>&1); rc=$?
expect_code "a lock left by a killed run is taken over" 0 "$rc" "$out"
expect_has "the entry landed" "- after a killed run" "$(cat "$R/stale.md")"

echo "note.sh and a writer that takes no lock"
# An editor that changes the note between the copy and the move must not be overwritten. The fake
# cp copies, then appends a line to the original, the way a second writer would.
F="$T/fakecp"; mkdir -p "$F"
real_cp=$(command -v cp)
cat >"$F/cp" <<EOF
#!/usr/bin/env bash
"$real_cp" "\$@" || exit 1
for a in "\$@"; do src=\$prev; prev=\$a; done
[ -n "\${FAKE_CP_TOUCH:-}" ] && [ "\$src" = "\$FAKE_CP_TOUCH" ] && echo "typed by an editor" >>"\$src"
exit 0
EOF
chmod +x "$F/cp"
printf 'top block\n' >"$R/edited.md"
out=$(FAKE_CP_TOUCH="$R/edited.md" PATH="$F:$PATH" "$NOTE" add "$R/edited.md" "mine" 2>&1); rc=$?
expect_code "add refuses when the note changed under it" 1 "$rc" "$out"
expect_has "the editor's line survives" "typed by an editor" "$(cat "$R/edited.md")"
expect_not "the entry was not written over it" "- mine" "$(cat "$R/edited.md")"

echo "note.sh clock"
# The stamp is UTC whatever the zone of the caller. XXX-9 is nine hours ahead of UTC.
a=$(date -u '+%Y-%m-%d %H:%M UTC'); got=$(TZ=XXX-9 "$NOTE" now); b=$(date -u '+%Y-%m-%d %H:%M UTC')
if [ "$got" = "$a" ] || [ "$got" = "$b" ]; then ok "now is UTC under another time zone"; else no "now is UTC under another time zone (got '$got', wanted '$a')"; fi
printf 'top block\n' >"$R/tz.md"
out=$(TZ=XXX-9 "$NOTE" add "$R/tz.md" "zone check" 2>&1); b2=$(date -u '+%Y-%m-%d %H:%M UTC')
h=$(grep '^## ' "$R/tz.md" | tail -n 1)
if [ "$h" = "## $b" ] || [ "$h" = "## $b2" ]; then ok "add stamps in UTC under another time zone"; else no "add stamps in UTC under another time zone (got '$h')"; fi

B="$T/badclock"; mkdir -p "$B"; printf '#!/bin/sh\nexit 1\n' >"$B/date"; chmod +x "$B/date"
printf 'top block\n' >"$R/clock.md"
out=$(PATH="$B:$PATH" "$NOTE" add "$R/clock.md" "x" 2>&1); rc=$?
expect_code "a clock that fails stops add" 1 "$rc" "$out"
expect_eq "nothing was written" "top block" "$(cat "$R/clock.md")"
out=$(NOTE_NOW="yesterday" "$NOTE" add "$R/clock.md" "x" 2>&1); rc=$?
expect_code "a stamp that is not a time stops add" 1 "$rc" "$out"
expect_eq "nothing was written then either" "top block" "$(cat "$R/clock.md")"
out=$(NOTE_NOW="yesterday" "$NOTE" rotate "$R/clock.md" --summary s 2>&1); rc=$?
expect_code "and stops rotate" 1 "$rc" "$out"

echo "note.sh on a symlinked note"
mkdir -p "$R/real" "$R/links"
printf 'top block\n' >"$R/real/goal.md"
ln -s ../real/goal.md "$R/links/goal.md"
out=$(NOTE_NOW="2026-03-01 10:00 UTC" "$NOTE" add "$R/links/goal.md" "through the link" 2>&1); rc=$?
expect_code "add through a symlink" 0 "$rc" "$out"
[ -L "$R/links/goal.md" ] && ok "the link is still a link" || no "the link is still a link"
expect_has "the target got the entry" "- through the link" "$(cat "$R/real/goal.md")"
out=$(NOTE_NOW="2026-03-01 11:00 UTC" "$NOTE" rotate "$R/links/goal.md" --summary s --carry c 2>&1); rc=$?
expect_code "rotate through a symlink" 0 "$rc" "$out"
[ -L "$R/links/goal.md" ] && ok "the link survives a rotate" || no "the link survives a rotate"
[ -f "$R/real/goal-log-2026-03-01.md" ] && ok "the rotated log sits next to the target" || no "the rotated log sits next to the target" "$(ls "$R/real" "$R/links")"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
