#!/usr/bin/env bash
# Tick or untick checkboxes in a GitHub issue body, with a backup and a guard on every byte.
#
#   tick.sh <issue> (--all | --match <text>... | --line <n>...) [options]
#
#   --all                  every unticked box
#   --match <text>         the one box whose line holds <text>, a fixed string, not a regex.
#                          Repeatable. The text must hit exactly one box, ticked or not. If that
#                          box is already ticked, it is reported and skipped. A text that hits
#                          two boxes is a refusal even when only one of them is open: a rerun
#                          of --match "#412" must never tick "#4123"
#   --line <n>             the n-th checkbox in the body, counting from 1. Repeatable
#   --untick               reverse the direction of all three
#   --repo <owner/repo>    passed to both gh calls. Default: gh's own (the current repository)
#   --dry-run              show the lines that would change, edit nothing
#   --backup-dir <dir>     where the body is saved before the edit
#
# A box is a list item with [ ], [x] or [X]: a bullet (-, *, +) or an ordered marker (1. or 1)),
# indented or inside a quote (> ). Lines inside a code fence (``` or ~~~) are never boxes, so
# template text is left alone. A box in a code block made by indentation alone is still counted.
#
# Saves the body as <backup-dir>/issue-<n>-<yyyymmddThhmmssZ>.before.md, builds the edited body in
# a .after.md next to it, and edits only when the two have the same lines and bytes and differ in
# nothing but the bracket character of the selected boxes. CRLF line ends survive. After the edit
# it reads the body back and compares, and on a mismatch prints the command that restores it.
# Just before the edit it reads the body once more and refuses if it changed since the backup, so
# a box someone else ticked meanwhile is not undone.
#
# Exit codes: 0 done or nothing to do, 1 refused by a guard or by the selection, 2 usage,
#             3 the body read back differs from what was sent.
# Env: TICK_BACKUP_DIR  backup dir when --backup-dir is not given
#                       (default ${XDG_STATE_HOME:-$HOME/.local/state}/claude-kit/issue-bodies)
set -u
export LC_ALL=C

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
die2() { echo "tick.sh: $*" >&2; echo "usage: tick.sh <issue> (--all | --match <text>... | --line <n>...) [--repo <owner/repo>] [--untick] [--dry-run] [--backup-dir <dir>]" >&2; exit 2; }
refuse() { echo "tick.sh: refused: $*. Nothing was edited." >&2; exit 1; }

# Never read and write the same file in one expression (such as `sed ... body.md >body.md`): the
# shell truncates the output file before the reader opens it, so the reader sees an empty file
# and an empty body goes up. A helper that did this once blanked eleven issue bodies. So the body
# is fetched into one file, the edit is built in a second file, and the second is checked against
# the first before anything is sent.

issue= repo= mode= untick= dry= backup_dir=
matches=()
picks=()
set_mode() {
  [ -z "$mode" ] || [ "$mode" = "$1" ] || die2 "use one selector: --all, --match or --line"
  mode=$1
}
while [ $# -gt 0 ]; do
  case $1 in
    --all) set_mode all; shift ;;
    --match)
      [ $# -ge 2 ] && [ -n "$2" ] || die2 "--match needs a text"
      set_mode match; matches+=("$2"); shift 2 ;;
    --line)
      [ $# -ge 2 ] || die2 "--line needs a number"
      case $2 in '' | *[!0-9]*) die2 "--line needs a number from 1, not '$2'" ;; esac
      [ $((10#$2)) -ge 1 ] || die2 "--line counts from 1"
      set_mode line; picks+=($((10#$2))); shift 2 ;;
    --repo) [ $# -ge 2 ] && [ -n "$2" ] || die2 "--repo needs <owner/repo>"; repo=$2; shift 2 ;;
    --untick) untick=1; shift ;;
    --dry-run) dry=1; shift ;;
    --backup-dir) [ $# -ge 2 ] && [ -n "$2" ] || die2 "--backup-dir needs a directory"; backup_dir=$2; shift 2 ;;
    -h | --help) usage ;;
    -*) die2 "unknown option: $1" ;;
    *) [ -z "$issue" ] || die2 "one issue at a time"; issue=${1#\#}; shift ;;
  esac
done
[ -n "$issue" ] || die2 "no issue number"
case $issue in *[!0-9]*) die2 "the issue must be a number, not '$issue'" ;; esac
[ -n "$mode" ] || die2 "no selector: pass --all, --match <text> or --line <n>"
command -v gh >/dev/null 2>&1 || { echo "tick.sh: gh is required" >&2; exit 2; }

ghr=()
[ -z "$repo" ] || ghr=(--repo "$repo")
if [ -n "$untick" ]; then verb=untick; want=' '; else verb=tick; want=x; fi
bytes() { echo $(( $(wc -c <"$1") )); }
lines() { echo $(( $(wc -l <"$1") )); }
same_body() { # a, b: equal, or equal but for one trailing newline
  cmp -s "$1" "$2" && return 0
  local sa sb big small
  sa=$(bytes "$1"); sb=$(bytes "$2")
  if [ $((sa - sb)) -eq 1 ]; then big=$1 small=$2
  elif [ $((sb - sa)) -eq 1 ]; then big=$2 small=$1
  else return 1; fi
  [ -z "$(tail -c 1 "$big")" ] && head -c "$(bytes "$small")" "$big" | cmp -s - "$small"
}

# 1. Back up the body. set -C never lets a run overwrite an earlier backup.
bdir=${backup_dir:-${TICK_BACKUP_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/claude-kit/issue-bodies}}
mkdir -p "$bdir" || { echo "tick.sh: cannot create $bdir" >&2; exit 1; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
stem="$bdir/issue-$issue-$stamp"
k=1
until ( set -C; : >"$stem.before.md" ) 2>/dev/null; do
  [ -e "$stem.before.md" ] || { echo "tick.sh: cannot write in $bdir" >&2; exit 1; }
  k=$((k + 1)); stem="$bdir/issue-$issue-$stamp-$k"
done
before=$stem.before.md after=$stem.after.md back=$stem.readback.md raw=$stem.raw
edited=
cleanup() { rm -f "$raw"; [ -n "$edited" ] || rm -f "$before" "$after" "$back"; }
trap cleanup EXIT
trap 'exit 130' INT TERM
restore="gh issue edit $issue${repo:+ --repo $(printf '%q' "$repo")} --body-file $(printf '%q' "$before")"

fetch() { # dest: the body as stored
  gh issue view "$issue" "${ghr[@]+"${ghr[@]}"}" --json body -q .body >"$raw" || return 1
  # gh -q prints the body and then a line end of its own. Drop that one byte, so the backup is
  # the body as stored and an edit does not add a line end to the issue on every run.
  if [ -s "$raw" ] && [ -z "$(tail -c 1 "$raw")" ]; then
    head -c $(( $(bytes "$raw") - 1 )) "$raw" >"$1"
  else
    cat "$raw" >"$1"
  fi
  rm -f "$raw"
}
fetch "$before" || refuse "cannot read the body of #$issue"
grep -q '[^[:space:]]' "$before" || refuse "the body of #$issue is empty"

# 2. Find the boxes. One line per box: index, line number, state (u for an empty box, else x or X).
# A box line: optional quote marks, a bullet or an ordered marker, then the brackets.
# [ \t\r\f\v] is [[:space:]] spelled out, for awks without character classes.
box_re='/^[ \t\r\f\v]*(>[ \t]*)*([-*+]|[0-9]+[.)]) \[[ xX]\] /'
# Sets st for every line: "" when it is not a box, u for an empty box, else x or X. Lines inside a
# code fence are never boxes.
scan='{ st = ""
  if ($0 ~ /^[ \t]*(>[ \t]*)*(```|~~~)/) infence = !infence
  else if (!infence && match($0, '"$box_re"')) { c = substr($0, RLENGTH - 2, 1); st = (c == " " ? "u" : c) } }'
boxes=$(awk "$scan"' st != "" { n++; print n "\t" NR "\t" st }' "$before")
total=0
box_ln=() box_st=()
while IFS=$'\t' read -r i ln st; do
  [ -n "$i" ] || continue
  box_ln[i]=$ln; box_st[i]=$st; total=$i
done <<<"$boxes"
[ "$total" -gt 0 ] || refuse "#$issue has no checkboxes"

is_source() { # state: is this box one the run would change?
  if [ -n "$untick" ]; then [ "$1" != u ]; else [ "$1" = u ]; fi
}
if [ -n "$untick" ]; then done_word="already unticked"; src_word=ticked; else done_word="already ticked"; src_word=unticked; fi
show() { sed -n "${1}p" "$before" | tr -d '\r'; }
selected=()
add_pick() {
  local s
  for s in "${selected[@]+"${selected[@]}"}"; do [ "$s" = "$1" ] && return; done
  selected+=("$1")
}

# 3. Select.
problems=
case $mode in
  all)
    for ((i = 1; i <= total; i++)); do is_source "${box_st[i]}" && add_pick "${box_ln[i]}"; done ;;
  line)
    for p in "${picks[@]}"; do
      if [ "$p" -gt "$total" ]; then problems+="--line $p: #$issue has $total checkboxes"$'\n'; continue; fi
      if is_source "${box_st[p]}"; then add_pick "${box_ln[p]}"
      else echo "$done_word, skipped: line ${box_ln[p]}: $(show "${box_ln[p]}")"; fi
    done ;;
  match)
    for t in "${matches[@]}"; do
      hits=$(TICK_NEEDLE=$t awk "$scan"' st != "" && index($0, ENVIRON["TICK_NEEDLE"]) { print NR "\t" st }' "$before")
      src=() oth=()
      while IFS=$'\t' read -r ln st; do
        [ -n "$ln" ] || continue
        if is_source "$st"; then src+=("$ln"); else oth+=("$ln"); fi
      done <<<"$hits"
      # Pick only when the text names one box in any state. With one open and one ticked box
      # both matching, the open one may not be the box that was meant: a rerun of a text that
      # ticked "#412" would go on to tick "#4123".
      nhits=$(( ${#src[@]} + ${#oth[@]} ))
      if [ "$nhits" -eq 0 ]; then
        problems+="--match '$t' fits no box"$'\n'
      elif [ "$nhits" -gt 1 ]; then
        problems+="--match '$t' fits $nhits boxes, make it unique:"$'\n'
        for ln in "${src[@]+"${src[@]}"}" "${oth[@]+"${oth[@]}"}"; do
          [ -n "$ln" ] && problems+="  line $ln: $(show "$ln")"$'\n'
        done
      elif [ ${#src[@]} -eq 1 ]; then
        add_pick "${src[0]}"
      else
        echo "$done_word, skipped: line ${oth[0]}: $(show "${oth[0]}")"
      fi
    done ;;
esac
[ -z "$problems" ] || { printf '%s' "$problems" >&2; refuse "the selection did not hold"; }
if [ ${#selected[@]} -eq 0 ]; then echo "nothing to $verb in #$issue"; exit 0; fi

# 4. Build the edited body in a second file, from the first.
trail=0
[ -z "$(tail -c 1 "$before")" ] && trail=1
TICK_LINES="${selected[*]}" TICK_WANT=$want awk -v trail="$trail" '
  BEGIN { n = split(ENVIRON["TICK_LINES"], a, " "); for (i = 1; i <= n; i++) sel[a[i]] = 1 }
  { line = $0
    if ((NR in sel) && match(line, '"$box_re"')) {
      p = RLENGTH - 2
      line = substr(line, 1, p - 1) ENVIRON["TICK_WANT"] substr(line, p + 1) }
    printf "%s%s", (NR > 1 ? "\n" : ""), line }
  END { if (NR > 0 && trail) printf "\n" }' "$before" >"$after" || refuse "could not build the edited body"

# 5. The guards. Each one compares the two files directly.
[ -s "$after" ] || refuse "the edited body is empty"
[ "$(lines "$after")" -eq "$(lines "$before")" ] \
  || refuse "the edited body has $(lines "$after") lines, the original $(lines "$before")"
[ "$(bytes "$after")" -eq "$(bytes "$before")" ] \
  || refuse "the edited body has $(bytes "$after") bytes, the original $(bytes "$before")"
report=$(TICK_OTHER=$after TICK_WANT=$want awk '
  BEGIN { other = ENVIRON["TICK_OTHER"]; want = ENVIRON["TICK_WANT"] }
  { a = $0
    if ((getline b < other) <= 0) { print "BAD line " NR ": the edited body ends early"; exit }
    if (a "" == b "") next
    if (!match(a, '"$box_re"')) { print "BAD line " NR ": not a checkbox line"; next }
    p = RLENGTH - 2; ca = substr(a, p, 1); cb = substr(b, p, 1)
    if (substr(a, 1, p - 1) "" != substr(b, 1, p - 1) "" || substr(a, p + 1) "" != substr(b, p + 1) "") {
      print "BAD line " NR ": more than the bracket character changed"; next }
    if (cb != want || (want == "x" ? (ca != " ") : (ca == " "))) { print "BAD line " NR ": [" ca "] became [" cb "]"; next }
    print "CHANGED " NR }' "$before")
bad=$(printf '%s\n' "$report" | grep '^BAD ' || true)
[ -z "$bad" ] || { printf '%s\n' "$bad" >&2; refuse "the edited body changes more than the selected boxes"; }
got=$(printf '%s\n' "$report" | sed -n 's/^CHANGED //p' | sort -n | tr '\n' ' ')
wanted=$(printf '%s\n' "${selected[@]}" | sort -n | tr '\n' ' ')
[ "$got" = "$wanted" ] \
  || refuse "the edited body changes lines ${got:-none}, the selection is lines $wanted"

if [ -n "$dry" ]; then
  for ln in $wanted; do
    echo "line $ln: $(show "$ln")"
    echo "     now: $(sed -n "${ln}p" "$after" | tr -d '\r')"
  done
  echo "dry run: would $verb ${#selected[@]} of $total boxes in #$issue, nothing edited"
  exit 0
fi

# 6. Read the body once more. If someone changed it since the backup, an edit built from the
# backup would undo their change.
fetch "$back" || refuse "cannot read the body of #$issue again before the edit"
cmp -s "$before" "$back" \
  || refuse "the body of #$issue changed since it was read, run again to work from the new body"

# 7. Edit, then believe only what reads back.
edited=1
if ! gh issue edit "$issue" "${ghr[@]+"${ghr[@]}"}" --body-file "$after" >/dev/null; then
  if gh issue view "$issue" "${ghr[@]+"${ghr[@]}"}" --json body -q .body >"$back" 2>/dev/null \
    && same_body "$before" "$back"; then
    edited=
    refuse "the edit call failed and the body is as it was"
  fi
  echo "tick.sh: the edit call failed and the body may have changed. Restore it with:" >&2
  echo "  $restore" >&2
  exit 3
fi
if ! gh issue view "$issue" "${ghr[@]+"${ghr[@]}"}" --json body -q .body >"$back"; then
  echo "tick.sh: edited #$issue, but cannot read it back. Check it, and restore it if needed with:" >&2
  echo "  $restore" >&2
  exit 3
fi
if ! same_body "$after" "$back"; then
  echo "tick.sh: the body of #$issue read back differs from what was sent:" >&2
  diff "$after" "$back" | head -n 20 | sed 's/^/  /' >&2
  echo "Sent: $after. Read back: $back. Restore the original with:" >&2
  echo "  $restore" >&2
  exit 3
fi
rm -f "$after" "$back"
echo "${verb}ed ${#selected[@]} of $total boxes in #$issue, backup $before"
