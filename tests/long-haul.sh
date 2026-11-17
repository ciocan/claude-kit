#!/usr/bin/env bash
# Tests for the long-haul scripts. Nothing here touches GitHub: merge-train.sh runs against a
# stub `gh` that serves canned answers from files.
#
#   tests/long-haul.sh            run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/plugins/flow/skills/long-haul/scripts"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
PASS=0
FAIL=0

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
wait_marker() { # log, name, seconds
  local n=0
  until grep -qF "== $2 exit " "$1" 2>/dev/null; do
    n=$((n + 1)); [ "$n" -gt $(( $3 * 5 )) ] && return 1; sleep 0.2
  done
}

echo "run-detached.sh and after.sh"
D="$T/runs"
export RUN_POLL_S=1 WAIT_POLL_S=1

out=$("$S/run-detached.sh" good --dir "$D" -- bash -c 'echo working; sleep 1; exit 0'); rc=$?
expect_code "launcher returns at once" 0 "$rc" "$out"
expect_has "launcher prints the log path" "$D/good.log" "$out"
out=$("$S/after.sh" good --dir "$D" -- echo follow-up-ran); rc=$?
expect_code "follow-up runs after exit 0" 0 "$rc" "$out"
expect_has "follow-up output present" "follow-up-ran" "$out"
expect_has "log ends with the marker" "== good exit 0" "$(tail -n 1 "$D/good.log")"
[ -f "$D/good.pid" ] && no "pid file removed after the run" || ok "pid file removed after the run"

"$S/run-detached.sh" bad --dir "$D" -- bash -c 'exit 3' >/dev/null
out=$("$S/after.sh" bad --dir "$D" -- echo must-not-run); rc=$?
expect_code "follow-up refused after exit 3" 1 "$rc" "$out"
expect_not "follow-up did not run" "must-not-run" "$out"
expect_has "marker carries the real exit code" "== bad exit 3" "$(cat "$D/bad.log")"

"$S/run-detached.sh" piped --dir "$D" -- bash -o pipefail -c 'false | tail -n 1' >/dev/null
wait_marker "$D/piped.log" piped 10
expect_has "a failure inside a pipe is not lost" "== piped exit 1" "$(cat "$D/piped.log")"

"$S/run-detached.sh" long --dir "$D" -- bash -c 'sleep 300 & echo "grandchild $!"; wait' >/dev/null
sleep 1.5
out=$("$S/run-detached.sh" long --dir "$D" -- true 2>&1); rc=$?
expect_code "second start of a running name is refused" 1 "$rc" "$out"
gc=$(sed -n 's/^grandchild //p' "$D/long.log")
touch "$D/long.stop"
wait_marker "$D/long.log" long 15
expect_has "stop file ends the run" "stopped by" "$(cat "$D/long.log")"
if [ -n "$gc" ] && kill -0 "$gc" 2>/dev/null; then no "stop reaches the grandchild"; kill "$gc"; else ok "stop reaches the grandchild"; fi

"$S/run-detached.sh" killed --dir "$D" -- sleep 300 >/dev/null
sleep 1.5
wrapper=$(cat "$D/killed.pid")
pkill -KILL -P "$wrapper" 2>/dev/null; kill -KILL "$wrapper" 2>/dev/null
sleep 0.5
out=$("$S/after.sh" killed --dir "$D" -- echo must-not-run); rc=$?
expect_code "a run killed without a marker is reported" 3 "$rc" "$out"

out=$(WAIT_MAX_S=2 "$S/after.sh" never --dir "$D" -- echo must-not-run); rc=$?
expect_code "the wait has a deadline" 4 "$rc" "$out"

echo "chain.sh"
C="$T/chain"
printf '# a comment\nfirst\techo one\nguard\ttest -f %s/go\nthird\techo three | tail -n 1\n' "$T" >"$T/steps.tsv"
out=$("$S/chain.sh" "$T/steps.tsv" --dir "$C" --dry-run); rc=$?
expect_code "dry run lists the steps" 0 "$rc" "$out"
expect_has "dry run shows the command" "test -f" "$out"
out=$("$S/chain.sh" "$T/steps.tsv" --dir "$C"); rc=$?
expect_code "chain stops at the failed guard" 1 "$rc" "$out"
expect_has "failure line names the step" "FAILED guard exit 1" "$out"
expect_has "failure line gives the resume command" "--from guard" "$out"
expect_has "STATUS holds the failure" "FAILED guard" "$(cat "$C/STATUS")"
[ -f "$C/third.log" ] && no "the step after the failure did not run" || ok "the step after the failure did not run"
touch "$T/go"
out=$("$S/chain.sh" "$T/steps.tsv" --dir "$C" --from guard); rc=$?
expect_code "resume from the failed step finishes" 0 "$rc" "$out"
expect_has "resume ran the rest" "DONE: 2 steps ok" "$out"
expect_not "resume skipped the finished step" "start first" "$out"
printf 'lost\tfalse | tail -n 1\n' >"$T/pipe.tsv"
out=$("$S/chain.sh" "$T/pipe.tsv" --dir "$T/chain2"); rc=$?
expect_code "a failure inside a step's pipe stops the chain" 1 "$rc" "$out"
out=$("$S/chain.sh" "$T/steps.tsv" --dir "$C" --from nope 2>&1); rc=$?
expect_code "an unknown --from is a usage error" 2 "$rc" "$out"
printf 'slow\tsleep 2\nnext\techo next\n' >"$T/stop.tsv"
( sleep 0.7; touch "$T/chain3/stop" ) &
out=$("$S/chain.sh" "$T/stop.tsv" --dir "$T/chain3"); rc=$?
expect_code "the stop file halts between steps" 3 "$rc" "$out"
expect_has "the stop line gives the resume command" "--from next" "$out"

echo "merge-train.sh (stub gh)"
G="$T/gh"; mkdir -p "$G/bin"
cat >"$G/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Canned GitHub. State lives in $GH_STUB as small JSON files.
d=$GH_STUB; q=; json=; pos=()
while [ $# -gt 0 ]; do
  case $1 in
    -q | --jq) q=$2; shift 2 ;;
    --json) json=$2; shift 2 ;;
    -R | --match-head-commit) shift 2 ;;
    --squash | --merge | --rebase | --delete-branch) shift ;;
    *) pos+=("$1"); shift ;;
  esac
done
emit() { if [ -n "$q" ]; then jq -r "$q"; else cat; fi; }
case "${pos[0]}:${pos[1]:-}" in
  repo:view) echo '{"nameWithOwner":"o/r"}' | emit ;;
  pr:view)
    n=${pos[2]}
    if [ "$json" = statusCheckRollup ]; then
      c=$(cat "$d/pr$n.calls" 2>/dev/null || echo 0); c=$((c + 1)); echo "$c" >"$d/pr$n.calls"
      f="$d/pr$n.checks.$c"; [ -f "$f" ] || f=$(ls "$d"/pr$n.checks.* | sort -t. -k3 -n | tail -n 1)
      cat "$f" | emit
    else
      cat "$d/pr$n.state" | emit
    fi ;;
  pr:merge)
    n=${pos[2]}; echo "merge $n" >>"$d/merges"
    mode=$(cat "$d/pr$n.merge" 2>/dev/null || echo ok)
    [ "$mode" = refuse ] && { echo "merge refused" >&2; exit 1; }
    [ "$mode" = silent ] && exit 0
    old=$(jq -r .object.sha "$d/base"); oid="c0ffee0$n"
    jq --arg o "$oid" '.state="MERGED" | .mergeCommit={oid:$o}' "$d/pr$n.state" >"$d/tmp" && mv "$d/tmp" "$d/pr$n.state"
    echo "{\"object\":{\"sha\":\"$oid\"}}" >"$d/base"
    parent=$old; [ "$mode" = moved ] && parent=deadbeef
    echo "{\"parents\":[{\"sha\":\"$parent\"}]}" >"$d/commit.$oid" ;;
  api:*)
    case ${pos[1]} in
      */git/ref/heads/*) cat "$d/base" | emit ;;
      */commits/*) cat "$d/commit.${pos[1]##*/}" | emit ;;
    esac ;;
esac
STUB
chmod +x "$G/bin/gh"
export PATH="$G/bin:$PATH" MERGE_TRAIN_SETTLE_S=0
GREEN='{"statusCheckRollup":[{"name":"test","status":"COMPLETED","conclusion":"SUCCESS"},{"context":"lint","state":"SUCCESS"}]}'
PENDING='{"statusCheckRollup":[{"name":"test","status":"IN_PROGRESS","conclusion":""},{"context":"lint","state":"SUCCESS"}]}'
RED='{"statusCheckRollup":[{"name":"test","status":"COMPLETED","conclusion":"FAILURE"},{"name":"bot","status":"COMPLETED","conclusion":"SUCCESS"}]}'
NONE='{"statusCheckRollup":[]}'
fresh() { # one stub world per scenario
  export GH_STUB="$T/world.$RANDOM$RANDOM"; mkdir -p "$GH_STUB"
  echo '{"object":{"sha":"base0000"}}' >"$GH_STUB/base"
}
pr() { # number, checks json, mergeable, draft
  echo "$2" >"$GH_STUB/pr$1.checks.1"
  echo "{\"state\":\"OPEN\",\"baseRefName\":\"main\",\"headRefOid\":\"head000$1\",\"mergeable\":\"${3:-MERGEABLE}\",\"isDraft\":${4:-false},\"mergeCommit\":null}" >"$GH_STUB/pr$1.state"
}
train() { "$S/merge-train.sh" --poll 0 "$@" 2>&1; }

fresh; pr 1 "$PENDING"; echo "$GREEN" >"$GH_STUB/pr1.checks.3"; pr 2 "$GREEN"
out=$(train 1 2); rc=$?
expect_code "two green PRs merge in order" 0 "$rc" "$out"
expect_has "it waited while a check was pending" "waiting: PENDING" "$out"
expect_has "it reports each merge" "MERGED #2 as c0ffee02 [2/2]" "$out"
expect_has "it ends with the summary line" "ALL MERGED: 2 of 2" "$out"
expect_has "the repository is detected" "in o/r" "$out"

fresh; pr 1 "$GREEN"; pr 2 "$RED"; pr 3 "$GREEN"
out=$(train 1 2 3); rc=$?
expect_code "a failed check stops the train" 1 "$rc" "$out"
expect_has "the stop line names the PR" "STOP [2/3] #2" "$out"
expect_has "the resume line lists what is left" "squash 2 3" "$out"
expect_has "the PR after the failure was not merged" "merge 1" "$(cat "$GH_STUB/merges")"
expect_not "the PR after the failure was not merged (3)" "merge 3" "$(cat "$GH_STUB/merges")"

fresh; pr 1 "$RED"
out=$(train --ignore-check test 1); rc=$?
expect_code "an ignored check does not block" 0 "$rc" "$out"

fresh; pr 1 "$NONE"
out=$(train 1); rc=$?
expect_code "no checks at all stops by default" 1 "$rc" "$out"
expect_has "it says how to allow that" "--allow-no-checks" "$out"
fresh; pr 1 "$NONE"
out=$(train --allow-no-checks 1); rc=$?
expect_code "no checks is accepted on request" 0 "$rc" "$out"

fresh; pr 1 "$GREEN" MERGEABLE true
out=$(train 1); rc=$?
expect_code "a draft is not merged" 1 "$rc" "$out"
expect_has "it says why" "it is a draft" "$out"

fresh; pr 1 "$GREEN" CONFLICTING
out=$(train 1); rc=$?
expect_code "a conflicting PR is not merged" 1 "$rc" "$out"
expect_has "it reports the mergeable state" "mergeable is CONFLICTING" "$out"

fresh; pr 1 "$GREEN"; echo refuse >"$GH_STUB/pr1.merge"
out=$(train 1); rc=$?
expect_code "a refused merge stops the train" 1 "$rc" "$out"

fresh; pr 1 "$GREEN"; echo silent >"$GH_STUB/pr1.merge"; pr 2 "$GREEN"
out=$(train 1 2); rc=$?
expect_code "a merge call that did not merge is caught" 1 "$rc" "$out"
expect_has "it trusts only the MERGED state" "does not report MERGED" "$out"
expect_not "the next PR was not touched" "merge 2" "$(cat "$GH_STUB/merges")"

fresh; pr 1 "$GREEN"; echo moved >"$GH_STUB/pr1.merge"; pr 2 "$GREEN"
out=$(train 1 2); rc=$?
expect_code "a base that moved under the squash stops the train" 1 "$rc" "$out"
expect_has "it says the PR did merge" "it merged, but main moved" "$out"
expect_has "resume starts at the next PR" "squash 2" "$out"

fresh; pr 1 "$GREEN"; pr 2 "$GREEN"
out=$(train --dry-run 1 2); rc=$?
expect_code "dry run succeeds" 0 "$rc" "$out"
[ -f "$GH_STUB/merges" ] && no "dry run merges nothing" "$(cat "$GH_STUB/merges")" || ok "dry run merges nothing"

fresh; pr 1 "$GREEN"; pr 2 "$GREEN"
out=$(train --after 'echo "hook $1 $2"; [ "$1" != 1 ]' 1 2); rc=$?
expect_code "a failed after-merge command stops the train" 1 "$rc" "$out"
expect_has "the hook received the PR and the commit" "hook 1 c0ffee01" "$out"
expect_has "resume skips the merged PR" "squash 2" "$out"

out=$(train --method fast 1); rc=$?
expect_code "an unknown method is a usage error" 2 "$rc" "$out"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
