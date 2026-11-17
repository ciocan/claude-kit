#!/usr/bin/env bash
# Run steps in order, each into its own log, and stop at the first failure.
#
#   chain.sh <steps-file> [--dir <dir>] [--from <step name>] [--dry-run]
#
# The steps file has one step per line: a name, a tab, then the command. Lines that start with #
# and empty lines are skipped. Put a guard in as a step of its own (a check that exits non-zero),
# so a failed guard stops the chain before the step it protects.
#
# <dir>/chain.log gets one line per event. <dir>/STATUS always holds the latest line.
# <dir>/<name>.log holds a step's full output. Stop between steps with: touch <dir>/stop
# After a stop or a failure, fix the cause and rerun with --from <step name>.
#
# Exit codes: 0 all steps ok, 1 a step failed, 2 usage, 3 stopped by the stop file, 130 interrupted.
set -u

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

[ $# -ge 1 ] || usage
steps=$1; shift
dir=${RUN_DIR:-$PWD/runs}/chain
from=
dry=
while [ $# -gt 0 ]; do
  case $1 in
    --dir) dir=${2:-}; shift 2 || usage ;;
    --from) from=${2:-}; shift 2 || usage ;;
    --dry-run) dry=1; shift ;;
    *) usage ;;
  esac
done
[ -f "$steps" ] || { echo "steps file not found: $steps" >&2; exit 2; }
mkdir -p "$dir" || exit 2

names=()
cmds=()
while IFS=$'\t' read -r n c || [ -n "$n" ]; do
  case $n in '' | \#*) continue ;; esac
  [ -n "${c:-}" ] || { echo "step '$n' has no command (name, a tab, the command)" >&2; exit 2; }
  names+=("$n")
  cmds+=("$c")
done <"$steps"
total=${#names[@]}
[ "$total" -gt 0 ] || { echo "no steps in $steps" >&2; exit 2; }

start=0
if [ -n "$from" ]; then
  start=-1
  for i in "${!names[@]}"; do [ "${names[$i]}" = "$from" ] && start=$i; done
  [ "$start" -ge 0 ] || { echo "--from '$from' is not a step in $steps" >&2; exit 2; }
fi

self="$0 $steps --dir $dir"
say() {
  local line
  line="$(date -u +%FT%TZ) $*"
  echo "$line"
  echo "$line" >>"$dir/chain.log"
  echo "$line" >"$dir/STATUS"
}
current=
trap 'say "INTERRUPTED at ${current:-start}. Resume: $self --from ${current:-${names[$start]}}"; exit 130' INT TERM

say "chain start: $((total - start)) of $total steps, from '${names[$start]}', logs in $dir${dry:+, dry run}"
rm -f "$dir/stop"
ok=0
for ((i = start; i < total; i++)); do
  current=${names[$i]}
  if [ -f "$dir/stop" ]; then
    say "STOP before '$current': stop file found. Resume: $self --from $current"
    exit 3
  fi
  if [ -n "$dry" ]; then
    echo "[$((i + 1))/$total] $current: ${cmds[$i]}"
    continue
  fi
  begun=$(date +%s)
  say "[$((i + 1))/$total] start $current"
  bash -o pipefail -c "${cmds[$i]}" >"$dir/$current.log" 2>&1 </dev/null
  rc=$?
  took=$(( $(date +%s) - begun ))
  if [ "$rc" -ne 0 ]; then
    tail -n 15 "$dir/$current.log" | sed 's/^/    /' >>"$dir/chain.log"
    say "FAILED $current exit $rc after ${took}s, chain stopped ($ok ok). See $dir/$current.log. Resume: $self --from $current"
    exit 1
  fi
  ok=$((ok + 1))
  say "[$((i + 1))/$total] ok $current (${took}s)"
done
[ -n "$dry" ] && { echo "dry run: $((total - start)) steps listed, nothing ran"; exit 0; }
say "DONE: $ok steps ok"
