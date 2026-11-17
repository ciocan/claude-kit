#!/usr/bin/env bash
# Start a long command detached from the session, so it survives the session ending.
#
#   run-detached.sh <name> [--dir <dir>] -- <command> [args...]
#
# Writes <dir>/<name>.log and <dir>/<name>.pid. The last line of the log is the marker
#   <UTC time> == <name> exit <rc>
# which watchers and after.sh wait for. Stop the run with: touch <dir>/<name>.stop
# A shell pipeline goes in as: -- bash -c '<pipeline>'
#
# Exit codes of this launcher: 0 started, 1 already running, 2 usage.
set -u

usage() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

[ $# -ge 3 ] || usage
name=$1; shift
dir=${RUN_DIR:-$PWD/runs}
if [ "${1:-}" = --dir ]; then dir=${2:-}; shift 2 || usage; fi
[ "${1:-}" = -- ] || usage
shift
[ $# -ge 1 ] || usage

log=$dir/$name.log
pidf=$dir/$name.pid
stopf=$dir/$name.stop
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

if [ "${_RUN_DETACHED:-}" != 1 ]; then
  mkdir -p "$dir" || exit 2
  if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
    echo "$name already runs (pid $(cat "$pidf")). Log: $log" >&2
    exit 1
  fi
  rm -f "$stopf"
  self=$(readlink -f "$0")
  _RUN_DETACHED=1 setsid nohup "$self" "$name" --dir "$dir" -- "$@" >>"$log" 2>&1 </dev/null &
  echo "$name started in the background (pid $!)."
  echo "  log:   $log"
  echo "  stop:  touch $stopf"
  echo "  watch: tail -n 0 -F $log | grep --line-buffered -E '== $name exit |FAILED|STOP'"
  exit 0
fi

# Detached from here on. The command gets its own process group, so a stop reaches its children.
echo $$ >"$pidf"
say "start $name in $PWD: $*"
setsid "$@" &
child=$!
trap 'kill -TERM -- "-$child" 2>/dev/null' TERM INT HUP
stopped=
while kill -0 "$child" 2>/dev/null; do
  if [ -z "$stopped" ] && [ -f "$stopf" ]; then
    stopped=1
    say "stop file seen, sending TERM to $name"
    kill -TERM -- "-$child" 2>/dev/null
  fi
  sleep "${RUN_POLL_S:-5}"
done
wait "$child"
rc=$?
[ -n "$stopped" ] && say "stopped by $stopf"
say "== $name exit $rc"
rm -f "$pidf"
exit "$rc"
