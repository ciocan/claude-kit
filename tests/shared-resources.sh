#!/usr/bin/env bash
# Tests for the orchestrate skill's shared-resource scripts, lock.py and claims.py. Everything runs
# in a temp folder with HOME pointed into it, so the real state folder is never touched.
#
#   tests/shared-resources.sh     run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/plugins/flow/skills/orchestrate/scripts"
L="${LOCK_CMD:-$S/lock.py}" # LOCK_CMD points the suite at another copy, to show a test catches a fault
C="$S/claims.py"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "  ok    $1"; }
no() { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/        /'; }
expect_code() { # name, wanted code, actual code, output
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (exit $3, wanted $2)" "$4"; fi
}
expect_eq() { # name, wanted, actual
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (got '$3', wanted '$2')"; fi
}
expect_has() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then ok "$1"; else no "$1 (missing: $2)" "$3"; fi
}
expect_not() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then no "$1 (found: $2)" "$3"; else ok "$1"; fi
}
expect_re() { # name, extended regex, haystack
  if printf '%s' "$3" | grep -qE -- "$2"; then ok "$1"; else no "$1 (no match: $2)" "$3"; fi
}
expect_file() { # name, path
  if [ -e "$2" ]; then ok "$1"; else no "$1 (missing: $2)"; fi
}
expect_gone() { # name, path
  if [ -e "$2" ]; then no "$1 (still there: $2)"; else ok "$1"; fi
}

# Nothing from the caller's environment may point the scripts at a real folder.
unset LOCK_DIR LOCK_OWNER CLAIMS_DIR CLAIMS_OWNER XDG_STATE_HOME
export HOME="$T/home" LOCK_POLL_S=1
mkdir -p "$HOME" "$T/work"
cd "$T/work" || exit 1

echo "lock.py"
D="$T/locks"

out=$("$L" acquire db --owner alpha --note "schema change" --dir "$D" 2>&1); rc=$?
expect_code "acquire a free lock" 0 "$rc" "$out"
expect_has "it prints ACQUIRED with the owner" "ACQUIRED db by alpha at " "$out"
missing=
for f in owner pid host time epoch note; do grep -q "^$f=" "$D/db.lock" || missing="$missing $f"; done
[ -z "$missing" ] && ok "the lock holds owner, pid, host, time, epoch, note" || no "lock files missing:$missing"
expect_has "the owner line holds the label" "owner=alpha" "$(cat "$D/db.lock")"
expect_re "the time is UTC" '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' "$(sed -n 's/^time=//p' "$D/db.lock")"

out=$("$L" acquire db --owner beta --dir "$D" 2>&1); rc=$?
expect_code "a second owner is refused" 1 "$rc" "$out"
expect_has "HELD names the first owner" "HELD db by alpha since " "$out"
expect_has "HELD shows the note" "note: schema change)" "$out"
expect_has "HELD says how a person forces it" "release db --force" "$out"
expect_has "the lock still belongs to the first owner" "owner=alpha" "$(cat "$D/db.lock")"

out=$("$L" acquire db --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "the same owner acquires again" 0 "$rc" "$out"
expect_has "it says ALREADY HELD" "ALREADY HELD db by alpha since " "$out"

out=$("$L" status db --dir "$D" 2>&1); rc=$?
expect_code "status of a held lock" 1 "$rc" "$out"
expect_has "status prints the HELD line" "HELD db by alpha" "$out"

out=$("$L" release db --owner beta --dir "$D" 2>&1); rc=$?
expect_code "release by another owner is refused" 1 "$rc" "$out"
expect_has "the refusal names the holder" "HELD db by alpha" "$out"
expect_file "the refused release left the lock" "$D/db.lock"

out=$("$L" release db --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "release by the owner" 0 "$rc" "$out"
expect_has "it prints RELEASED" "RELEASED db" "$out"
expect_gone "the lock file is gone" "$D/db.lock"

out=$("$L" status db --dir "$D" 2>&1); rc=$?
expect_code "status of a free lock" 0 "$rc" "$out"
expect_has "status prints FREE" "FREE db" "$out"

out=$("$L" release db --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "release of a free lock" 0 "$rc" "$out"
expect_has "it prints FREE" "FREE db" "$out"

"$L" acquire db --owner alpha --dir "$D" >/dev/null 2>&1
out=$("$L" release db --force --dir "$D" 2>&1); rc=$?
expect_code "release --force takes any holder's lock" 0 "$rc" "$out"
expect_has "it names who held it" "FORCED release of db, was held by alpha since " "$out"
expect_gone "the forced lock is gone" "$D/db.lock"

out=$("$L" acquire db --dir "$D" 2>&1); rc=$?
expect_code "acquire without an owner label" 2 "$rc" "$out"
expect_has "it says why a label is required" "LOCK_OWNER" "$out"
expect_gone "no lock was taken without a label" "$D/db.lock"
out=$("$L" release db --dir "$D" 2>&1); rc=$?
expect_code "release without an owner label" 2 "$rc" "$out"

out=$(LOCK_OWNER=gamma "$L" acquire db --dir "$D" 2>&1); rc=$?
expect_code "LOCK_OWNER stands in for --owner" 0 "$rc" "$out"
expect_has "the env label is the owner" "ACQUIRED db by gamma" "$out"
LOCK_OWNER=gamma "$L" release db --dir "$D" >/dev/null 2>&1

out=$("$L" acquire 'a/b' --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "a name with a slash is a usage error" 2 "$rc" "$out"
out=$("$L" acquire 'has space' --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "a name with a space is a usage error" 2 "$rc" "$out"
out=$("$L" grab db --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "an unknown verb is a usage error" 2 "$rc" "$out"
out=$("$L" acquire db --owner alpha --wait soon --dir "$D" 2>&1); rc=$?
expect_code "a wait that is not a number is a usage error" 2 "$rc" "$out"
expect_gone "the bad calls took no lock" "$D/db.lock"

: >"$D/half.lock"
out=$("$L" status half --dir "$D" 2>&1); rc=$?
expect_code "a half-written lock reads as held" 1 "$rc" "$out"
expect_has "its owner is unknown" "HELD half by unknown" "$out"
out=$("$L" acquire half --owner alpha --dir "$D" 2>&1); rc=$?
expect_code "a half-written lock cannot be acquired" 1 "$rc" "$out"
out=$("$L" release half --owner unknown --dir "$D" 2>&1); rc=$?
expect_code "the label 'unknown' does not release it" 1 "$rc" "$out"
out=$("$L" release half --force --dir "$D" 2>&1); rc=$?
expect_code "a half-written lock yields to --force" 0 "$rc" "$out"

"$L" acquire old --owner alpha --note "left behind" --dir "$D" >/dev/null 2>&1
sed "s/^epoch=.*/epoch=$(( $(date +%s) - 3 * 3600 - 600 ))/" "$D/old.lock" >"$D/old.lock.new" && mv "$D/old.lock.new" "$D/old.lock"
out=$("$L" acquire old --owner beta --dir "$D" 2>&1); rc=$?
expect_code "an old lock is still held" 1 "$rc" "$out"
expect_has "it shows the age in hours" "(3h 10m, note: left behind)" "$out"
expect_has "the old lock keeps its owner" "owner=alpha" "$(cat "$D/old.lock")"

"$L" acquire busy --owner alpha --dir "$D" >/dev/null 2>&1
start=$(date +%s)
out=$("$L" acquire busy --owner beta --wait 2 --dir "$D" 2>&1); rc=$?
took=$(( $(date +%s) - start ))
expect_code "a wait that runs out" 1 "$rc" "$out"
expect_has "it ends with the HELD line" "HELD busy by alpha" "$out"
[ "$took" -ge 2 ] && ok "it waited the full time" || no "it waited the full time (${took}s)"

( sleep 1; "$L" release busy --owner alpha --dir "$D" >/dev/null 2>&1 ) &
out=$("$L" acquire busy --owner beta --wait 10 --dir "$D" 2>&1); rc=$?
wait
expect_code "a wait ends when the holder releases" 0 "$rc" "$out"
expect_has "the waiter holds it now" "ACQUIRED busy by beta" "$out"

for i in 1 2 3 4 5 6 7 8; do
  ( "$L" acquire race --owner "r$i" --dir "$D" >"$T/race.$i.out" 2>&1; echo $? >"$T/race.$i.rc" ) &
done
wait
wins=$(cat "$T"/race.*.rc | grep -c '^0$')
[ "$wins" = 1 ] && ok "eight racing acquires, exactly one wins" || no "eight racing acquires, exactly one wins ($wins won)"
winner=$(grep -l '^ACQUIRED' "$T"/race.*.out | sed 's/.*race\.\([0-9]*\)\.out/r\1/')
expect_has "the winner's label is in the lock" "owner=$winner" "$(cat "$D/race.lock")"

out=$("$L" acquire home --owner alpha 2>&1); rc=$?
expect_code "acquire with the default folder" 0 "$rc" "$out"
expect_file "the default folder is under HOME" "$HOME/.local/state/claude-kit/locks/home.lock"
"$L" release home --owner alpha >/dev/null 2>&1
out=$(XDG_STATE_HOME="$T/xdg" "$L" acquire x --owner alpha 2>&1); rc=$?
expect_file "XDG_STATE_HOME moves the folder" "$T/xdg/claude-kit/locks/x.lock"
out=$(LOCK_DIR="$T/envlocks" "$L" acquire x --owner alpha 2>&1); rc=$?
expect_file "LOCK_DIR moves the folder" "$T/envlocks/x.lock"

echo "claims.py"
K="$T/claims"

out=$("$C" claim api feat/a@abc123 "first deploy" --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "claim a resource" 0 "$rc" "$out"
expect_file "the claim file is <resource>/<owner>.claim" "$K/api/alpha.claim"
claim=$(cat "$K/api/alpha.claim")
for k in owner=alpha resource=api ref=feat/a@abc123 time= epoch= host= "note=first deploy"; do
  expect_has "the claim has $k" "$k" "$claim"
done
out=$("$C" list --dir "$K" 2>&1); rc=$?
expect_code "list" 0 "$rc" "$out"
expect_re "list shows resource, owner, ref, time, age, note" \
  '^api  alpha  feat/a@abc123  [0-9T:-]+Z  [0-9]+s  first deploy$' "$out"

out=$("$C" claim api feat/a@def456 --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "claim again" 0 "$rc" "$out"
out=$("$C" list api --dir "$K" 2>&1)
expect_has "the new ref replaced the old one" "feat/a@def456" "$out"
expect_not "the old ref is gone" "abc123" "$out"
n=$(ls -A "$K/api" | grep -c .)
[ "$n" = 1 ] && ok "one file per owner, no temp files left" || no "one file per owner ($n files)" "$(ls -a "$K/api")"

"$C" claim api feat/b@777 --owner beta --dir "$K" >/dev/null 2>&1
f="$K/api/beta.claim"
sed "s/^epoch=.*/epoch=$(( $(date +%s) - 7200 ))/" "$f" >"$T/beta.tmp" && mv "$T/beta.tmp" "$f"
out=$("$C" list api --dir "$K" 2>&1)
expect_has "two owners hold one resource (alpha)" "api  alpha  feat/a@def456" "$out"
expect_has "two owners hold one resource (beta)" "api  beta  feat/b@777" "$out"
[ "$(printf '%s\n' "$out" | head -n 1 | cut -d' ' -f3)" = beta ] && ok "list is oldest first" || no "list is oldest first" "$out"
expect_has "the older claim shows its age in hours" "2h 0m" "$out"

out=$("$C" check api --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "check with another owner's claim" 1 "$rc" "$out"
expect_has "check names the other owner" "api  beta  feat/b@777" "$out"
expect_not "check leaves me out" "api  alpha" "$out"
expect_has "check says what to do" "OTHERS HOLD api: push the union of these refs and yours, or wait" "$out"

out=$("$C" check api --owner gamma --dir "$K" 2>&1); rc=$?
expect_code "check by a third owner sees both" 1 "$rc" "$out"
expect_has "it lists alpha" "api  alpha" "$out"

out=$("$C" check web --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "check on an unclaimed resource" 0 "$rc" "$out"
expect_has "it says CLEAR" "CLEAR web: no other claims" "$out"
"$C" claim solo v1 --owner alpha --dir "$K" >/dev/null 2>&1
out=$("$C" check solo --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "my own claim alone is clear" 0 "$rc" "$out"

out=$("$C" release api --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "release my claim" 0 "$rc" "$out"
expect_has "it says RELEASED" "RELEASED api for alpha" "$out"
expect_gone "my claim file is gone" "$K/api/alpha.claim"
expect_file "the other owner's claim stays" "$K/api/beta.claim"
out=$("$C" release api --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "release without a claim" 0 "$rc" "$out"
expect_has "it says NO CLAIM" "NO CLAIM api for alpha" "$out"

out=$("$C" list solo --dir "$K" 2>&1)
expect_has "list filtered by resource shows it" "solo  alpha  v1" "$out"
expect_not "list filtered by resource hides the rest" "api" "$out"
out=$("$C" list --dir "$T/claims-empty" 2>&1); rc=$?
expect_code "list with no claims" 0 "$rc" "$out"
expect_has "it says no claims" "no claims" "$out"

"$C" claim notes v2 deployed after   the "migration  ran" --owner alpha --dir "$K" >/dev/null 2>&1
expect_has "a note in several words is kept" "note=deployed after the migration  ran" "$(cat "$K/notes/alpha.claim")"
out=$("$C" list notes --dir "$K" 2>&1)
expect_has "list shows the whole note" "deployed after the migration  ran" "$out"

out=$("$C" claim api v9 --dir "$K" 2>&1); rc=$?
expect_code "claim without an owner label" 2 "$rc" "$out"
expect_has "it says why a label is required" "CLAIMS_OWNER" "$out"
out=$("$C" check api --dir "$K" 2>&1); rc=$?
expect_code "check without an owner label" 2 "$rc" "$out"
out=$("$C" release api --dir "$K" 2>&1); rc=$?
expect_code "release without an owner label" 2 "$rc" "$out"
out=$("$C" claim 'a/b' v1 --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "a resource with a slash is a usage error" 2 "$rc" "$out"
out=$("$C" claim .. v1 --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "the resource '..' is a usage error" 2 "$rc" "$out"
out=$("$C" claim api v1 --owner 'two words' --dir "$K" 2>&1); rc=$?
expect_code "an owner with a space is a usage error" 2 "$rc" "$out"
out=$("$C" claim api "$(printf 'line1\nline2')" --owner alpha --dir "$K" 2>&1); rc=$?
expect_code "a ref with a newline is a usage error" 2 "$rc" "$out"
expect_gone "the bad calls wrote nothing" "$K/api/alpha.claim"

out=$(LOCK_OWNER=lo "$C" claim fb v1 --dir "$K" 2>&1); rc=$?
expect_code "LOCK_OWNER stands in when CLAIMS_OWNER is unset" 0 "$rc" "$out"
expect_file "the claim is under the LOCK_OWNER label" "$K/fb/lo.claim"
CLAIMS_OWNER=co LOCK_OWNER=lo "$C" claim fb v2 --dir "$K" >/dev/null 2>&1
expect_file "CLAIMS_OWNER wins over LOCK_OWNER" "$K/fb/co.claim"

out=$("$C" claim home v1 --owner alpha 2>&1); rc=$?
expect_code "claim with the default folder" 0 "$rc" "$out"
expect_file "the default folder is under HOME" "$HOME/.local/state/claude-kit/claims/home/alpha.claim"
"$C" release home --owner alpha >/dev/null 2>&1
CLAIMS_DIR="$T/envclaims" "$C" claim x v1 --owner alpha >/dev/null 2>&1
expect_file "CLAIMS_DIR moves the folder" "$T/envclaims/x/alpha.claim"

echo "nothing written outside the temp folder"
want="$HOME/.local
$HOME/.local/state
$HOME/.local/state/claude-kit
$HOME/.local/state/claude-kit/claims
$HOME/.local/state/claude-kit/claims/home
$HOME/.local/state/claude-kit/locks"
got=$(find "$HOME" -mindepth 1 | sort)
[ "$got" = "$want" ] && ok "HOME holds only the default folders" || no "HOME holds only the default folders" "$got"
got=$(find "$T/work" -mindepth 1)
[ -z "$got" ] && ok "nothing was written in the working folder" || no "nothing was written in the working folder" "$got"

echo "lock.py --wait with a leading zero"
# 08 is not a valid octal number. It once broke the arithmetic and a free lock read as held.
out=$("$L" acquire zero --owner alpha --wait 08 --dir "$D" 2>&1); rc=$?
expect_code "--wait 08 on a free lock acquires it" 0 "$rc" "$out"
expect_has "it says so" "ACQUIRED zero by alpha" "$out"
expect_not "no arithmetic error" "value too great" "$out"
out=$(LOCK_POLL_S=1 "$L" acquire zero --owner beta --wait 01 --dir "$D" 2>&1); rc=$?
expect_code "--wait 01 on a held lock gives up" 1 "$rc" "$out"
expect_has "it waited one second, not zero or eight" "WAITED 1s for zero" "$out"

echo "lock.py under contention"
# Six workers take the lock in turn, each waiting for the one before. A lock built on mkdir let
# two in at once here: with the Rust coreutils, two mkdir calls on one path can both exit 0.
C="$T/contend"; mkdir -p "$C"
worker() { # label
  LOCK_POLL_S=0.05 "$L" acquire turn --owner "$1" --wait 60 --dir "$C/locks" >/dev/null 2>&1 || { echo "FAILED $1" >>"$C/trace"; return; }
  echo "IN $1" >>"$C/trace"; sleep 0.02; echo "OUT $1" >>"$C/trace"
  "$L" release turn --owner "$1" --dir "$C/locks" >/dev/null 2>&1
}
overlaps=0; missing=0
for round in 1 2 3 4 5; do
  : >"$C/trace"
  for w in a b c d e f; do worker "w$w" & done
  wait
  awk '$1 == "IN" { if (held) bad = 1; held = 1 } $1 == "OUT" { held = 0 } $1 == "FAILED" { bad = 1 } END { exit bad }' "$C/trace" || overlaps=$((overlaps + 1))
  [ "$(grep -c '^IN ' "$C/trace")" -eq 6 ] || missing=$((missing + 1))
done
expect_eq "never two holders at once, five rounds of six workers" 0 "$overlaps"
expect_eq "every worker got its turn" 0 "$missing"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
