#!/usr/bin/env bash
# Hold a named lock on a shared resource, across sessions, worktrees and short-lived shells.
#
#   lock.sh acquire <name> [--owner <label>] [--note <text>] [--wait <seconds>] [--dir <dir>]
#   lock.sh release <name> [--owner <label>] [--force] [--dir <dir>]
#   lock.sh status  <name> [--dir <dir>]
#
# The lock is the file <dir>/<name>.lock with the lines owner=, pid=, host=, time=, epoch= and
# note=. The shell creates it with noclobber, which opens it with O_EXCL, so exactly one caller
# wins. It is not a mkdir: where coreutils is the Rust rewrite (uutils 0.10), two mkdir calls on
# one path at the same moment can both exit 0. Ownership is the label, not a pid: every shell an
# agent runs is new, so pass the same label each time. The holder may acquire again. A lock is
# never broken for its age. The owner releases it, or a person decides and runs release with
# --force. A lock file without an owner line counts as held by "unknown".
#
# Env: LOCK_OWNER is the label when --owner is absent. LOCK_DIR is the folder (default
# $XDG_STATE_HOME/claude-kit/locks, else ~/.local/state/claude-kit/locks). LOCK_POLL_S is the
# poll interval for --wait (default 5).
#
# Exit codes: 0 ok, 1 held by someone else or the wait ran out, 2 usage.
set -u

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
die() { echo "lock.sh: $*" >&2; exit 2; }

[ $# -ge 2 ] || usage
cmd=$1; shift
case $cmd in acquire | release | status) ;; *) usage ;; esac

state=${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}
dir=${LOCK_DIR:-${state:+$state/claude-kit/locks}}
owner=${LOCK_OWNER:-}
name= note= wait= force= dir_arg=
while [ $# -gt 0 ]; do
  case $1 in
    --owner) [ $# -ge 2 ] || usage; owner=$2; shift 2 ;;
    --note) [ $# -ge 2 ] || usage; note=$2; shift 2 ;;
    --wait) [ $# -ge 2 ] || usage; wait=$2; shift 2 ;;
    --dir) [ $# -ge 2 ] || usage; dir=$2; printf -v dir_arg ' --dir %q' "$2"; shift 2 ;;
    --force) force=1; shift ;;
    -h | --help | --*) usage ;;
    *) [ -z "$name" ] || die "unexpected argument: $1"; name=$1; shift ;;
  esac
done

[ -n "$name" ] || usage
[[ $name =~ ^[A-Za-z0-9._-]+$ ]] || die "bad lock name '$name': use letters, digits, dot, dash, underscore"
case $cmd in
  acquire) [ -z "$force" ] || die "--force belongs to release" ;;
  release) [ -z "$note$wait" ] || die "--note and --wait belong to acquire" ;;
  status) [ -z "$note$wait$force" ] || die "status takes only a name and --dir" ;;
esac
if [ "$cmd" = acquire ] || { [ "$cmd" = release ] && [ -z "$force" ]; }; then
  [ -n "$owner" ] || die "an owner label is required: pass --owner <label> or set LOCK_OWNER.
Every command runs in a new shell, so a pid cannot show who holds the lock. The label does,
so use the same label to acquire and to release."
fi
[ -z "$wait" ] || [[ $wait =~ ^[0-9]+$ ]] || die "--wait takes whole seconds, got '$wait'"
# 08 is not octal here. Without this the arithmetic below fails and a free lock reads as held.
[ -z "$wait" ] || wait=$((10#$wait))
poll=${LOCK_POLL_S:-5}
[[ $poll =~ ^[0-9]+([.][0-9]+)?$ ]] || die "LOCK_POLL_S must be a number of seconds, got '$poll'"
[ -n "$dir" ] || die "no lock folder: set LOCK_DIR or HOME, or pass --dir"
mkdir -p "$dir" || die "cannot create the lock folder $dir"
lock=$dir/$name.lock
note=${note//$'\n'/ }
owner=${owner//$'\n'/ }

readf() { # field of the lock, default when missing or empty
  local v
  v=$(sed -n "s/^$1=//p" "$lock" 2>/dev/null | head -n 1) || v=
  printf '%s' "${v:-$2}"
}

age() { # seconds as a short readable age
  local s=$1
  [ "$s" -ge 0 ] || s=0
  if [ "$s" -lt 60 ]; then echo "${s}s"
  elif [ "$s" -lt 3600 ]; then echo "$((s / 60))m"
  elif [ "$s" -lt 86400 ]; then echo "$((s / 3600))h $((s % 3600 / 60))m"
  else echo "$((s / 86400))d $((s % 86400 / 3600))h"; fi
}

held() { # print the HELD line and how to release
  local o t e n a="age unknown"
  o=$(readf owner unknown); t=$(readf time unknown); e=$(readf epoch ''); n=$(readf note none)
  [[ $e =~ ^[0-9]+$ ]] && a=$(age $(( $(date +%s) - e )))
  echo "HELD $name by $o since $t ($a, note: $n)"
  echo "  It is never broken for age. The owner releases it: $0 release $name --owner $o$dir_arg"
  echo "  or a person decides it is abandoned and runs: $0 release $name --force$dir_arg"
}

try_acquire() { # 0 taken now or already ours, 1 held by another
  local i t
  local e h
  for i in 1 2 3; do
    t=$(date -u +%Y-%m-%dT%H:%M:%SZ); e=$(date +%s)
    h=${HOSTNAME:-$(hostname 2>/dev/null || echo unknown)}
    if ( set -C
      printf 'owner=%s\npid=%s\nhost=%s\ntime=%s\nepoch=%s\nnote=%s\n' \
        "$owner" "$PPID" "$h" "$t" "$e" "$note" >"$lock" ) 2>/dev/null; then
      echo "ACQUIRED $name by $owner at $t"
      return 0
    fi
    # Released between the create and this check: try again.
    [ -e "$lock" ] || continue
    if [ "$(readf owner '')" = "$owner" ]; then
      echo "ALREADY HELD $name by $owner since $(readf time unknown)"
      return 0
    fi
    return 1
  done
  die "cannot create $lock"
}

case $cmd in
  acquire)
    deadline=$(( $(date +%s) + ${wait:-0} ))
    while :; do
      try_acquire && exit 0
      if [ -z "$wait" ] || [ "$(date +%s)" -ge "$deadline" ]; then
        [ -z "$wait" ] || echo "WAITED ${wait}s for $name, still held."
        held
        exit 1
      fi
      sleep "$poll"
    done ;;
  release)
    if [ ! -e "$lock" ]; then echo "FREE $name"; exit 0; fi
    o=$(readf owner unknown); t=$(readf time unknown)
    if [ -n "$force" ]; then
      rm -f "$lock" || { echo "could not remove $lock" >&2; exit 1; }
      echo "FORCED release of $name, was held by $o since $t"
      exit 0
    fi
    if [ "$(readf owner '')" = "$owner" ]; then
      rm -f "$lock" || { echo "could not remove $lock" >&2; exit 1; }
      echo "RELEASED $name"
      exit 0
    fi
    held
    exit 1 ;;
  status)
    if [ -e "$lock" ]; then held; exit 1; fi
    echo "FREE $name"
    exit 0 ;;
esac
