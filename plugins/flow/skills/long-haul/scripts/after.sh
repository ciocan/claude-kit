#!/usr/bin/env bash
# Run a follow-up only after a detached run reported success.
#
#   after.sh <name> [--dir <dir>] -- <follow-up command> [args...]
#
# Waits for the marker line "== <name> exit <rc>" that run-detached.sh writes to <dir>/<name>.log.
# The follow-up starts only when <rc> is 0. Anything else stops with a line that says why.
# WAIT_MAX_S bounds the wait (default 86400). WAIT_POLL_S sets the poll interval (default 60).
#
# Exit codes: the follow-up's own code, or 1 the run failed, 3 the run died without a marker,
# 4 no marker by the deadline, 2 usage.
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
deadline=$(( $(date +%s) + ${WAIT_MAX_S:-86400} ))
ts() { date -u +%FT%TZ; }

echo "$(ts) == after $name: waiting for its exit line in $log"
while :; do
  line=$(grep -a -F "== $name exit " "$log" 2>/dev/null | tail -n 1)
  [ -n "$line" ] && break
  if [ -f "$pidf" ] && ! kill -0 "$(cat "$pidf")" 2>/dev/null; then
    # One more look: the marker is written just before the pid file is removed.
    line=$(grep -a -F "== $name exit " "$log" 2>/dev/null | tail -n 1)
    [ -n "$line" ] && break
    echo "$(ts) == after $name: STOP, the process is gone and left no exit line. Follow-up not run."
    exit 3
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "$(ts) == after $name: STOP, no exit line by the deadline. Follow-up not run."
    exit 4
  fi
  sleep "${WAIT_POLL_S:-60}"
done

rc=${line##* }
if [ "$rc" != 0 ]; then
  echo "$(ts) == after $name: STOP, it ended with exit $rc. Follow-up not run."
  exit 1
fi
echo "$(ts) == after $name: ok, starting the follow-up: $*"
exec "$@"
