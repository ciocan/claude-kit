#!/usr/bin/env bash
# Tests for tick.py. Nothing here touches GitHub: tick.py runs against a stub `gh` that serves an
# issue body from a file as JSON and stores what an edit sends. The guards that no outside fault
# can reach are tested in tests/py/test_tick.py, which this suite runs and counts.
#
#   tests/tick.sh             run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TICK="$ROOT/plugins/flow/skills/ship-pr/scripts/tick.py"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
PASS=0
FAIL=0
unset TICK_BACKUP_DIR

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
py_suite() { # file under tests/py: run it and add its ok and FAIL lines to the counts
  local out rc fails
  out=$(python3 -B "$ROOT/tests/py/$1" 2>&1); rc=$?
  printf '%s\n' "$out"
  PASS=$((PASS + $(printf '%s\n' "$out" | grep -c '^  ok    ')))
  fails=$(printf '%s\n' "$out" | grep -c '^  FAIL  ')
  FAIL=$((FAIL + fails))
  if [ "$rc" != 0 ] && [ "$fails" = 0 ]; then no "tests/py/$1 ran to the end (exit $rc)"; fi
}

G="$T/gh"; mkdir -p "$G/bin"
cat >"$G/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Canned GitHub issue. The body lives in $GH_STUB/body and every call is logged to $GH_STUB/calls.
# Marker files in $GH_STUB change the behaviour:
#   view-fails   issue view exits 1
#   empty        issue view serves an empty body
#   mangle       issue edit stores the body with its first line changed
#   edit-fails   issue edit exits 1 and stores nothing
#   peer-edit    a file whose content replaces the body just before the second view, the way
#                another session's edit would land between the read and the write
#   slow         issue view takes 0.3 seconds, so two runs at once overlap
d=$GH_STUB
echo "gh $*" >>"$d/calls"
pos=(); bf= json= jq=
while [ $# -gt 0 ]; do
  case $1 in
    --body-file) bf=$2; shift 2 ;;
    --json) json=$2; shift 2 ;;
    -q | --jq) jq=$2; shift 2 ;;
    --repo | -R) shift 2 ;;
    *) pos+=("$1"); shift ;;
  esac
done
# Like `gh issue view --json body`: one JSON object, the body a string inside it.
json_body() { python3 -B -c 'import json, sys; print(json.dumps({"body": sys.stdin.buffer.read().decode("utf-8")}))'; }
case "${pos[0]:-}:${pos[1]:-}" in
  issue:view)
    [ "$json" = body ] && [ -z "$jq" ] || { echo "stub gh: view wants --json body and no --jq: $*" >&2; exit 9; }
    [ -f "$d/slow" ] && sleep 0.3
    [ -f "$d/view-fails" ] && { echo "HTTP 502: Bad Gateway" >&2; exit 1; }
    [ -f "$d/empty" ] && { printf '' | json_body; exit 0; }
    n=$(( $(cat "$d/views" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$d/views"
    [ -f "$d/peer-edit" ] && [ "$n" -eq 2 ] && cp "$d/peer-edit" "$d/body"
    json_body <"$d/body" ;;
  issue:edit)
    [ -f "$d/edit-fails" ] && { echo "HTTP 422" >&2; exit 1; }
    if [ -f "$d/mangle" ]; then sed '1s/^/edited by a bot: /' "$bf" >"$d/body.new"; else cp "$bf" "$d/body.new"; fi
    mv "$d/body.new" "$d/body"
    echo "https://github.com/o/r/issues/${pos[2]}" ;;
  *) echo "stub gh: unexpected call: $*" >&2; exit 9 ;;
esac
STUB
chmod +x "$G/bin/gh"
export PATH="$G/bin:$PATH"

B1='## Tasks
- [ ] write the parser
- [x] read the spec
- [ ] write the tests
- [ ] ship the parser docs
Text with [ ] brackets that is not a box.'

fresh() { # body text; one stub world per scenario
  export GH_STUB="$T/world.$RANDOM$RANDOM"; mkdir -p "$GH_STUB"
  export TICK_BACKUP_DIR="$GH_STUB/backups"
  printf '%s\n' "$1" >"$GH_STUB/body"
  cp "$GH_STUB/body" "$GH_STUB/served" # the body as stored, before any edit
}
tick() { "$TICK" "$@" 2>&1; }
edits() { grep -c '^gh issue edit' "$GH_STUB/calls" 2>/dev/null || true; }
body() { cat "$GH_STUB/body"; }
line() { sed -n "$1p" "$GH_STUB/body"; }

echo "tick.py selection"
fresh "$B1"
out=$(tick 5 --all); rc=$?
expect_code "--all ticks every unticked box" 0 "$rc" "$out"
expect_has "it reports the count" "ticked 3 of 4 boxes in #5, backup $TICK_BACKUP_DIR/issue-5-" "$out"
expect_eq "box 1 ticked" "- [x] write the parser" "$(line 2)"
expect_eq "box 3 ticked" "- [x] write the tests" "$(line 4)"
expect_eq "box 4 ticked" "- [x] ship the parser docs" "$(line 5)"
expect_eq "the non-box line is untouched" "Text with [ ] brackets that is not a box." "$(line 6)"
expect_eq "one edit call" 1 "$(edits)"
backup=$(printf '%s\n' "$out" | sed -n 's/.*, backup //p')
if [ -f "$backup" ]; then ok "the backup file exists"; else no "the backup file exists" "$out"; fi
expect_same "the backup equals the body as stored" "$GH_STUB/served" "$backup"
expect_eq "only the backup is left in the backup dir" 1 "$(ls "$TICK_BACKUP_DIR" | wc -l | tr -d ' ')"

fresh "$B1"
out=$(tick 5 --match "write the tests"); rc=$?
expect_code "one --match" 0 "$rc" "$out"
expect_has "one of four" "ticked 1 of 4 boxes" "$out"
sed '4s/\[ \]/[x]/' "$GH_STUB/served" >"$T/want"
expect_same "only that line changed" "$T/want" "$GH_STUB/body"

fresh "$B1"
out=$(tick 5 --match "write the parser" --match "docs"); rc=$?
expect_code "two --match" 0 "$rc" "$out"
sed -e '2s/\[ \]/[x]/' -e '5s/\[ \]/[x]/' "$GH_STUB/served" >"$T/want"
expect_same "both lines changed, nothing else" "$T/want" "$GH_STUB/body"

fresh "$B1"
out=$(tick 5 --match "deploy"); rc=$?
expect_code "a --match with no hit is refused" 1 "$rc" "$out"
expect_has "it says so" "--match 'deploy' fits no box" "$out"
expect_same "the body is unchanged" "$GH_STUB/served" <(body)
expect_eq "no edit call" 0 "$(edits)"

fresh "$B1"
out=$(tick 5 --match "the p.rser"); rc=$?
expect_code "--match is a fixed string, not a regex" 1 "$rc" "$out"

fresh "$B1"
out=$(tick 5 --match "parser"); rc=$?
expect_code "an ambiguous --match is refused" 1 "$rc" "$out"
expect_has "it lists the first candidate" "line 2: - [ ] write the parser" "$out"
expect_has "it lists the second candidate" "line 5: - [ ] ship the parser docs" "$out"
expect_eq "no edit call" 0 "$(edits)"

fresh "$B1"
out=$(tick 5 --match "read the spec"); rc=$?
expect_code "a --match on an already ticked box is not an error" 0 "$rc" "$out"
expect_has "it reports the box" "already ticked, skipped: line 3: - [x] read the spec" "$out"
expect_has "and that there is nothing to do" "nothing to tick in #5" "$out"
expect_eq "no edit call" 0 "$(edits)"
out=$(tick 5 --match "read the spec" --match "tests"); rc=$?
expect_code "an already ticked box next to a fresh one" 0 "$rc" "$out"
expect_has "the fresh one is ticked" "ticked 1 of 4 boxes" "$out"

fresh "$B1"
out=$(tick 5 --line 1 --line 3); rc=$?
expect_code "--line" 0 "$rc" "$out"
sed -e '2s/\[ \]/[x]/' -e '4s/\[ \]/[x]/' "$GH_STUB/served" >"$T/want"
expect_same "--line counts checkboxes, not lines" "$T/want" "$GH_STUB/body"
out=$(tick 5 --line 2); rc=$?
expect_code "--line on a ticked box" 0 "$rc" "$out"
expect_has "it is skipped" "nothing to tick in #5" "$out"

fresh "$B1"
out=$(tick 5 --line 9); rc=$?
expect_code "--line out of range is refused" 1 "$rc" "$out"
expect_has "it says how many there are" "#5 has 4 checkboxes" "$out"
expect_eq "no edit call" 0 "$(edits)"

fresh "$B1"
out=$(tick 5 --untick --all); rc=$?
expect_code "--untick --all" 0 "$rc" "$out"
expect_has "it reports the untick" "unticked 1 of 4 boxes" "$out"
expect_eq "the ticked box is open again" "- [ ] read the spec" "$(line 3)"
out=$(tick 5 --untick --match "read the spec"); rc=$?
expect_code "--untick --match on an open box" 0 "$rc" "$out"
expect_has "it is reported as already unticked" "already unticked, skipped" "$out"

fresh "$B1"
out=$(tick 5 --all --dry-run); rc=$?
expect_code "--dry-run" 0 "$rc" "$out"
expect_has "it shows the old line" "line 2: - [ ] write the parser" "$out"
expect_has "it shows the new line" "now: - [x] write the parser" "$out"
expect_has "it says nothing was edited" "nothing edited" "$out"
expect_eq "no edit call" 0 "$(edits)"
expect_same "the body is unchanged" "$GH_STUB/served" <(body)

echo "tick.py bodies"
fresh "$B1"; touch "$GH_STUB/empty"
out=$(tick 5 --all); rc=$?
expect_code "an empty body is refused" 1 "$rc" "$out"
expect_eq "no edit call" 0 "$(edits)"

fresh "$B1"; touch "$GH_STUB/view-fails"
out=$(tick 5 --all); rc=$?
expect_code "a view that fails is refused" 1 "$rc" "$out"
expect_has "it says it cannot read" "cannot read the body of #5" "$out"
expect_eq "no edit call" 0 "$(edits)"
expect_eq "no backup is left" 0 "$(ls "$TICK_BACKUP_DIR" | wc -l | tr -d ' ')"

fresh "$(printf '## Tasks\r\n- [ ] one\r\n- [X] two\r\n  * [ ] three\r\nTrailing words, [ ] and all\r\n')"
out=$(tick 5 --all); rc=$?
expect_code "a CRLF body" 0 "$rc" "$out"
expect_has "it ticks both open boxes" "ticked 2 of 3 boxes" "$out"
sed 's/\[[xX]\]/[ ]/' "$GH_STUB/served" >"$T/a"
sed 's/\[[xX]\]/[ ]/' "$GH_STUB/body" >"$T/b"
expect_same "every byte but the ticked characters survives" "$T/a" "$T/b"
expect_eq "the CRs are still there" 5 "$(tr -cd '\r' <"$GH_STUB/body" | wc -c | tr -d ' ')"
expect_eq "the capital X is kept" "- [X] two"$'\r' "$(line 3)"

NEST='Intro
- [ ] top
  - [ ] nested
    * [ ] deeper star
+ [x] plus done
-[ ] not a box
- [] not a box
	- [ ] tab indent'
fresh "$NEST"
out=$(tick 5 --all); rc=$?
expect_code "nested lists and * bullets" 0 "$rc" "$out"
expect_has "four open boxes of five" "ticked 4 of 5 boxes" "$out"
expect_eq "the nested box" "  - [x] nested" "$(line 3)"
expect_eq "the star box" "    * [x] deeper star" "$(line 4)"
expect_eq "the tab-indented box" "	- [x] tab indent" "$(line 8)"
expect_eq "a dash without a space is not a box" "-[ ] not a box" "$(line 6)"
fresh "$NEST"
out=$(tick 5 --line 3); rc=$?
expect_code "--line counts nested boxes" 0 "$rc" "$out"
expect_eq "the third box is the star one" "    * [x] deeper star" "$(line 4)"

fresh 'Just prose.
- a list item
- [] almost a box'
out=$(tick 5 --all); rc=$?
expect_code "a body with no checkboxes is refused" 1 "$rc" "$out"
expect_has "it says why" "#5 has no checkboxes" "$out"
expect_eq "no edit call" 0 "$(edits)"

fresh '- [x] a
- [X] b'
out=$(tick 5 --all); rc=$?
expect_code "nothing to tick" 0 "$rc" "$out"
expect_has "it says so" "nothing to tick in #5" "$out"
expect_eq "no edit call" 0 "$(edits)"

echo "tick.py after the edit"
fresh "$B1"; touch "$GH_STUB/mangle"
out=$(tick 5 --all); rc=$?
expect_code "a read-back that differs exits 3" 3 "$rc" "$out"
expect_has "it prints the restore command" "gh issue edit 5 --body-file $TICK_BACKUP_DIR/issue-5-" "$out"
restore=$(printf '%s\n' "$out" | grep '^  gh issue edit' | sed 's/^  //')
expect_has "the restore command points at the backup" ".before.md" "$restore"
rm -f "$GH_STUB/mangle"
eval "$restore" >/dev/null
expect_same "the restore command brings the body back" "$GH_STUB/served" "$GH_STUB/body"

fresh "$B1"; touch "$GH_STUB/edit-fails"
out=$(tick 5 --all); rc=$?
expect_code "a failed edit call that changed nothing is refused" 1 "$rc" "$out"
expect_has "it says the body is as it was" "the body is as it was" "$out"

fresh "$B1"
out=$(tick 5 --repo o/r --match "tests"); rc=$?
expect_code "--repo" 0 "$rc" "$out"
expect_eq "--repo reaches both views before the edit, the edit and the read-back" 4 "$(grep -c -- '--repo o/r' "$GH_STUB/calls")"
expect_eq "four gh calls in all" 4 "$(wc -l <"$GH_STUB/calls" | tr -d ' ')"

fresh "$B1"
out=$(tick 5 --all --backup-dir "$GH_STUB/elsewhere"); rc=$?
expect_code "--backup-dir" 0 "$rc" "$out"
expect_has "the backup goes there" "backup $GH_STUB/elsewhere/issue-5-" "$out"

# The guard on the edited body, with a shortened body among others, is in tests/py/test_tick.py.

echo "tick.py --match names one box"
# A rerun must not tick a different box. "#412" is ticked, "#4123" is open, and both hold the text.
fresh '## Epic
- [x] #412 parser
- [ ] #4123 docs
- [ ] #500 tests'
out=$(tick 5 --match "#412"); rc=$?
expect_code "a text that fits one ticked and one open box is refused" 1 "$rc" "$out"
expect_has "it counts both" "--match '#412' fits 2 boxes" "$out"
expect_has "it lists the ticked one" "line 2: - [x] #412 parser" "$out"
expect_has "it lists the open one" "line 3: - [ ] #4123 docs" "$out"
expect_eq "no edit call" 0 "$(edits)"
expect_same "the body is unchanged" "$GH_STUB/served" <(body)
out=$(tick 5 --match "#412 "); rc=$?
expect_code "the full text of the ticked box is a no-op" 0 "$rc" "$out"
expect_has "it says already ticked" "already ticked, skipped: line 2" "$out"
expect_eq "#4123 is still open" "- [ ] #4123 docs" "$(line 3)"
out=$(tick 5 --match "#4123"); rc=$?
expect_code "a text that fits one box ticks it" 0 "$rc" "$out"
expect_eq "#4123 is ticked" "- [x] #4123 docs" "$(line 3)"

echo "tick.py code fences, ordered and quoted items"
fresh '## Plan
- [ ] real one
```md
- [ ] template line, not a task
```
1. [ ] ordered item
2) [ ] ordered with a bracket
> - [ ] quoted item
~~~
* [ ] another template
~~~
- [ ] real two'
out=$(tick 5 --line 2); rc=$?
expect_code "--line 2 is the second box the page shows" 0 "$rc" "$out"
expect_eq "the ordered item is box 2" "1. [x] ordered item" "$(line 6)"
expect_eq "the fenced line was not counted" "- [ ] template line, not a task" "$(line 4)"
out=$(tick 5 --all); rc=$?
expect_code "--all" 0 "$rc" "$out"
expect_has "it sees five boxes, not seven" "ticked 4 of 5 boxes" "$out"
expect_eq "the bracket form is ticked" "2) [x] ordered with a bracket" "$(line 7)"
expect_eq "the quoted item is ticked" "> - [x] quoted item" "$(line 8)"
expect_eq "the last real box is ticked" "- [x] real two" "$(line 12)"
expect_eq "the first fence is untouched" "- [ ] template line, not a task" "$(line 4)"
expect_eq "the second fence is untouched" "* [ ] another template" "$(line 10)"
out=$(tick 5 --match "template line"); rc=$?
expect_code "--match cannot reach into a fence" 1 "$rc" "$out"
expect_has "it fits no box" "fits no box" "$out"

echo "tick.py and an edit by someone else"
# A peer ticks another box between this run's read and its write. Writing the old body back
# would undo it.
fresh "$B1"
sed '5s/\[ \]/[x]/' "$GH_STUB/body" >"$GH_STUB/peer-edit"
out=$(tick 5 --line 1); rc=$?
expect_code "a body that changed since the read is refused" 1 "$rc" "$out"
expect_has "it says why" "changed since it was read" "$out"
expect_eq "no edit call" 0 "$(edits)"
expect_same "the peer's body stands" "$GH_STUB/peer-edit" <(body)
rm -f "$GH_STUB/peer-edit"
out=$(tick 5 --line 1); rc=$?
expect_code "the next run works from the new body" 0 "$rc" "$out"
expect_eq "this run's box is ticked" "- [x] write the parser" "$(line 2)"
expect_eq "the peer's box is still ticked" "- [x] ship the parser docs" "$(line 5)"

echo "tick.py line ends"
# The body is read from JSON, byte for byte. gh -q, used before, printed a line end of its own
# after the body, and an edit that sent it back would grow the stored body on every run.
fresh "$B1"
size0=$(wc -c <"$GH_STUB/body" | tr -d ' ')
out=$(tick 5 --line 1); rc=$?
expect_code "first run" 0 "$rc" "$out"
out=$(tick 5 --line 3); rc=$?
expect_code "second run" 0 "$rc" "$out"
expect_eq "two runs leave the body the same size" "$size0" "$(wc -c <"$GH_STUB/body" | tr -d ' ')"
export GH_STUB="$T/world.noeol"; mkdir -p "$GH_STUB"; export TICK_BACKUP_DIR="$GH_STUB/backups"
printf -- '- [ ] one\n- [ ] two' >"$GH_STUB/body"
out=$(tick 5 --all); rc=$?
expect_code "a body with no final line end" 0 "$rc" "$out"
expect_eq "it is stored without one" "- [x] one
- [x] twoEND" "$(cat "$GH_STUB/body"; printf END)"

echo "tick.py usage"
fresh "$B1"
out=$(tick --all); rc=$?
expect_code "no issue is a usage error" 2 "$rc" "$out"
out=$(tick 5); rc=$?
expect_code "no selector is a usage error" 2 "$rc" "$out"
out=$(tick 5 --all --match x); rc=$?
expect_code "two selectors is a usage error" 2 "$rc" "$out"
out=$(tick 5 --line 0); rc=$?
expect_code "--line 0 is a usage error" 2 "$rc" "$out"
out=$(tick 5 6 --all); rc=$?
expect_code "two issues is a usage error" 2 "$rc" "$out"
[ -f "$GH_STUB/calls" ] && no "usage errors make no gh call" "$(cat "$GH_STUB/calls")" || ok "usage errors make no gh call"

echo "tick.py runs at once"
# Two runs on one issue, each ticking its own box. Without the per-issue lock, the second run read
# the body before the first one's edit, saw it change before its own edit, and refused.
fresh "$B1"; touch "$GH_STUB/slow"
( "$TICK" 5 --match "write the parser" >"$GH_STUB/run.1" 2>&1; echo $? >"$GH_STUB/run.1.rc" ) &
( "$TICK" 5 --match "write the tests" >"$GH_STUB/run.2" 2>&1; echo $? >"$GH_STUB/run.2.rc" ) &
wait
expect_eq "the first run exits 0" 0 "$(cat "$GH_STUB/run.1.rc")"
expect_eq "the second run exits 0" 0 "$(cat "$GH_STUB/run.2.rc")"
expect_eq "the first run's box is ticked" "- [x] write the parser" "$(line 2)"
expect_eq "the second run's box is ticked" "- [x] write the tests" "$(line 4)"
expect_eq "two edit calls" 2 "$(edits)"
expect_eq "two backups, no lock file left" 2 "$(ls -A "$TICK_BACKUP_DIR" | wc -l | tr -d ' ')"

echo "tick.py guards (tests/py/test_tick.py)"
py_suite test_tick.py

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
