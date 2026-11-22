#!/usr/bin/env bash
# Keep a program note's log: stamp every entry from the machine's clock, and rotate the log.
#
#   note.sh add    <note-file> <bullet text>...   one bullet per argument. A single "-" reads
#                                                 the bullets from stdin, one per line
#   note.sh rotate <note-file> --summary <text>... [--carry <text>...] [--dry-run]
#   note.sh check  <note-file>
#   note.sh now
#
# The log is everything from the first "## yyyy-mm-dd hh:mm UTC" heading to the end of the file.
# Everything above it is the top block, and this script never changes it. The format is in
# references/program-note.md.
#
# add     appends one entry stamped with the current UTC time. There is no way to pass a time.
#         Warns on stderr when the log has grown past NOTE_MAX_LINES lines.
# rotate  moves the log to <note>-log-<yyyy-mm-dd>.md next to the note (-2, -3 when taken) and
#         leaves one entry: where the log went, one to five --summary bullets, then a --carry
#         bullet for each live item (running jobs, agents, holds, what the user owes).
# check   prints the log's size, its first and last stamps, and the entries that go back in time.
# now     prints the stamp add would use.
#
# add and rotate hold a lock file (<dir>/.<note>.lock) from the read to the move, so two writers
# at once both land. A lock left by a killed run is taken over. A note that is a symlink is
# followed: the target is rewritten and the link stays.
#
# Exit codes: 0 ok, 1 a check failed or nothing could be written, 2 usage.
# Env: NOTE_MAX_LINES  log lines before add warns and check fails (default 300)
#      NOTE_LOCK_WAIT_S  seconds to wait for another writer before giving up (default 10)
#      NOTE_NOW        replaces the clock. It exists for tests only and a session must never set
#                      it: times typed from memory are what this script is here to stop.
set -u
export LC_ALL=C

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
die2() { echo "note.sh: $*" >&2; exit 2; }

# Every write goes the same way: build the new content in a second file next to the note, check
# it, then mv it over the note. Never read and write the same file in one expression (such as
# `sed ... note >note`): the shell truncates the output file before the reader opens it, and the
# content is gone before anything reads it.

STAMP_RE='^## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC'
max=${NOTE_MAX_LINES:-300}
case $max in '' | *[!0-9]*) die2 "NOTE_MAX_LINES must be a whole number, not '$max'" ;; esac

now() {
  if [ -n "${NOTE_NOW:-}" ]; then printf '%s\n' "$NOTE_NOW"; else date -u '+%Y-%m-%d %H:%M UTC'; fi
}
stamp_now() { # sets STAMP, or stops: an entry without a real time is worse than no entry
  STAMP=$(now) || STAMP=
  [[ $STAMP =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}\ UTC$ ]] \
    || { echo "note.sh: no valid time from the clock (got '$STAMP'). Nothing was written." >&2; exit 1; }
}
first_entry() { grep -nE "$STAMP_RE" "$1" | head -n 1 | cut -d: -f1; }
count_lines() { awk 'END { print NR }' "$1"; }
top_of() { awk -v n="$2" 'NR > n { exit } { print }' "$1"; } # head -n 0 is not portable
bytes() { echo $(( $(wc -c <"$1") )); }
one_line() { local s=${1//$'\r'/ }; printf '%s' "${s//$'\n'/ }"; }

# Temp files live next to the note so the final mv is a rename on one file system.
tmps=()
own_rotated=
lock= have_lock=
cleanup() {
  [ ${#tmps[@]} -eq 0 ] || rm -f "${tmps[@]}"
  [ -z "$own_rotated" ] || rm -f "$own_rotated"
  [ -z "$have_lock" ] || rm -f "$lock"
}
# One writer at a time. Without this, two adds at once each copied the note, appended to their
# copy and moved it into place, and the second move threw the first entry away while both runs
# reported success.
#
# The lock is a file the shell itself creates with noclobber, which opens it with O_EXCL. It is
# not a mkdir: where coreutils is the Rust rewrite (uutils 0.10), two mkdir calls on one path at
# the same moment can both exit 0, and a mkdir lock then lets two writers in.
take_lock() {
  lock="$dir/.$file.lock"
  local tries=0 limit=$(( ${NOTE_LOCK_WAIT_S:-10} * 10 )) pid
  until ( set -C; echo $$ >"$lock" ) 2>/dev/null; do
    pid=$(cat "$lock" 2>/dev/null) || pid=
    if [ -n "$pid" ] && ! ps -p "$pid" >/dev/null 2>&1; then
      # Left by a run that was killed. One waiter at a time may clear it, and only while it still
      # names that dead process, so a lock taken meanwhile is never removed.
      if ( set -C; : >"$lock.clear" ) 2>/dev/null; then
        [ "$(cat "$lock" 2>/dev/null)" != "$pid" ] || rm -f "$lock"
        rm -f "$lock.clear"
        continue
      fi
    fi
    if [ "$tries" -ge "$limit" ]; then
      echo "note.sh: another writer holds $lock (pid ${pid:-unknown}). Nothing was written." >&2
      exit 1
    fi
    sleep 0.1
    tries=$((tries + 1))
  done
  have_lock=1
}
trap cleanup EXIT
trap 'exit 130' INT TERM
newtmp() { # sets REPLY to a fresh temp file in $dir
  REPLY=$(mktemp "$dir/.$file.XXXXXX") || { echo "note.sh: cannot create a temp file in $dir" >&2; exit 1; }
  tmps+=("$REPLY")
}
fail() { echo "note.sh: $*. The note is unchanged." >&2; exit 1; }

open_note() { # sets note, dir, file, base
  note=$1
  [ -f "$note" ] || die2 "note not found: $note (note.sh does not create notes)"
  # Follow a symlink to the file it names. A move over the link would replace the link, and the
  # real note would stop receiving entries.
  local link hops=0
  while [ -L "$note" ] && [ "$hops" -lt 8 ]; do
    link=$(readlink "$note")
    case $link in /*) note=$link ;; *) note="$(dirname "$note")/$link" ;; esac
    hops=$((hops + 1))
  done
  dir=$(dirname "$note")
  file=$(basename "$note")
  base=${file%.md}
}

cmd_add() {
  open_note "$1"; shift
  local raw=() lines=() b line
  if [ $# -eq 1 ] && [ "$1" = - ]; then
    while IFS= read -r line || [ -n "$line" ]; do raw+=("$line"); done
  else
    raw=("$@")
  fi
  for b in "${raw[@]+"${raw[@]}"}"; do
    b=$(one_line "$b")
    [ -n "${b//[[:space:]]/}" ] || continue
    case $b in '- '*) ;; *) b="- $b" ;; esac
    lines+=("$b")
  done
  [ ${#lines[@]} -gt 0 ] || die2 "no bullet to add"

  local stamp tmp size start n want
  stamp_now; stamp=$STAMP
  take_lock
  newtmp; tmp=$REPLY
  cp -p "$note" "$tmp" || fail "cannot copy $note"
  {
    # A last line without its newline would swallow the blank line.
    if [ -s "$note" ] && [ -n "$(tail -c 1 "$note")" ]; then echo; fi
    echo
    echo "## $stamp"
    printf '%s\n' "${lines[@]}"
  } >>"$tmp"
  size=$(bytes "$note")
  head -c "$size" "$tmp" | cmp -s - "$note" || fail "the new copy does not start with the old note"
  mv "$tmp" "$note" || fail "cannot move the new copy over $note"
  # Believe the note, not the move: the entry must be its last lines.
  want=$(printf '## %s\n' "$stamp"; printf '%s\n' "${lines[@]}")
  [ "$(tail -n $(( ${#lines[@]} + 1 )) "$note")" = "$want" ] \
    || { echo "note.sh: the entry is not at the end of $note. Check the note." >&2; exit 1; }
  rm -f "$lock"; have_lock=

  start=$(first_entry "$note")
  n=$(( $(count_lines "$note") - start + 1 ))
  echo "added ${#lines[@]} lines at $stamp (log $n lines)"
  if [ "$n" -gt "$max" ]; then
    echo "note.sh: the log is $n lines, over $max. Rotate it: note.sh rotate $note --summary \"...\"" >&2
  fi
}

cmd_check() {
  open_note "$1"
  local start kb n report bad
  kb=$(( ($(bytes "$note") + 1023) / 1024 ))
  start=$(first_entry "$note")
  if [ -z "$start" ]; then
    echo "no log entries in $note ($kb KB)"
    return 0
  fi
  n=$(( $(count_lines "$note") - start + 1 ))
  echo "log: $n lines, limit $max$([ "$n" -gt "$max" ] && echo ", OVER THE LIMIT")"
  echo "note: $kb KB"
  # grep -n prints "<line>:<heading>". The heading has colons of its own, so split at the first.
  report=$(grep -nE "$STAMP_RE" "$note" | awk '
    { i = index($0, ":"); ln = substr($0, 1, i - 1); h = substr($0, i + 1); s = substr(h, 4, 20)
      if (NR == 1) first = s
      if (NR > 1 && s < prev) { bad++; list = list sprintf("  line %d: %s\n", ln, h) }
      prev = s; last = s }
    END { printf "entries: %d, first %s, last %s\n", NR, first, last
          printf "out of order: %d\n%s", bad + 0, list }')
  printf '%s\n' "$report"
  bad=$(printf '%s\n' "$report" | sed -n 's/^out of order: //p')
  [ "$n" -le "$max" ] && [ "$bad" = 0 ]
}

cmd_rotate() {
  open_note "$1"; shift
  local summaries=() carries=() dry=
  while [ $# -gt 0 ]; do
    case $1 in
      --summary | --carry)
        [ $# -ge 2 ] && [ -n "${2//[[:space:]]/}" ] || die2 "$1 needs a text"
        if [ "$1" = --summary ]; then summaries+=("$(one_line "$2")"); else carries+=("$(one_line "$2")"); fi
        shift 2 ;;
      --dry-run) dry=1; shift ;;
      *) die2 "unknown rotate option: $1" ;;
    esac
  done
  [ ${#summaries[@]} -ge 1 ] || die2 "rotate needs at least one --summary (what the period achieved, what it left open)"
  [ ${#summaries[@]} -le 5 ] || die2 "at most five --summary lines, got ${#summaries[@]}"

  local start total n stamp day name i
  stamp_now; stamp=$STAMP
  [ -n "$dry" ] || take_lock
  start=$(first_entry "$note")
  if [ -z "$start" ]; then echo "nothing to rotate"; return 0; fi
  total=$(count_lines "$note")
  n=$((total - start + 1))
  day=${stamp%% *}
  name="$base-log-$day.md"
  i=1
  while [ -e "$dir/$name" ]; do i=$((i + 1)); name="$base-log-$day-$i.md"; done

  local entry=("## $stamp" "- Rotated: $n log lines up to here moved to $name")
  local s
  for s in "${summaries[@]}"; do entry+=("- Summary: $s"); done
  for s in "${carries[@]+"${carries[@]}"}"; do entry+=("- Carried forward: $s"); done

  if [ -n "$dry" ]; then
    echo "dry run: would move $n log lines (lines $start to $total) to $dir/$name"
    echo "the top block ($((start - 1)) lines) stays, followed by this entry:"
    printf '  %s\n' "${entry[@]}"
    return 0
  fi

  local top log rotated new
  newtmp; top=$REPLY
  newtmp; log=$REPLY
  top_of "$note" $((start - 1)) >"$top"
  tail -n +"$start" "$note" >"$log"
  cat "$top" "$log" | cmp -s - "$note" || fail "the note does not split cleanly into top block and log"

  # 1. The rotated file. set -C refuses to take over a file that appeared meanwhile.
  rotated="$dir/$name"
  ( set -C; : >"$rotated" ) 2>/dev/null || fail "cannot create $rotated"
  own_rotated=$rotated
  { printf '# %s log, rotated %s\n\n' "$base" "$stamp"; cat "$log"; } >>"$rotated" \
    || fail "cannot write $rotated"
  [ "$(count_lines "$log")" -eq "$n" ] && [ "$(count_lines "$rotated")" -eq $((n + 2)) ] \
    || fail "the rotated file does not hold $n log lines"
  tail -n +3 "$rotated" | cmp -s - "$log" || fail "the rotated file differs from the log"

  # 2 and 3. The new main note. cp -p first, so the rewrite keeps the note's mode.
  newtmp; new=$REPLY
  cp -p "$note" "$new" || fail "cannot copy $note"
  { cat "$top"; printf '%s\n' "${entry[@]}"; } >"$new"
  [ "$(first_entry "$new")" = "$start" ] && top_of "$new" $((start - 1)) | cmp -s - "$top" \
    || fail "the new note's top block differs from the old one"
  cat "$top" "$log" | cmp -s - "$note" || fail "the note changed while rotating"
  mv "$new" "$note" || fail "cannot move the new note over $note"
  own_rotated=

  echo "rotated $n log lines to $rotated"
  if [ ${#carries[@]} -eq 0 ]; then
    echo "note.sh: no --carry given. Carry forward what is still live: running jobs, agents, holds, what the user owes. Add them now: note.sh add $note \"Carried forward: ...\"" >&2
  fi
}

[ $# -ge 1 ] || usage
cmd=$1; shift
case $cmd in
  now) [ $# -eq 0 ] || usage; stamp_now; echo "$STAMP" ;;
  add) [ $# -ge 1 ] || usage; cmd_add "$@" ;;
  rotate) [ $# -ge 1 ] || usage; cmd_rotate "$@" ;;
  check) [ $# -eq 1 ] || usage; cmd_check "$1" ;;
  -h | --help) usage ;;
  *) echo "note.sh: unknown command: $cmd" >&2; usage ;;
esac
