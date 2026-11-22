#!/usr/bin/env bash
# Check that the paths a text cites exist on a git ref, before an issue or a brief sends an agent
# to read them.
#
#   cited-paths.sh <ref> [--repo <dir>] [--path <path>]... [<file>... | -]
#
#   <ref>            the ref the agents' worktrees are cut from, for example origin/dev
#   --repo <dir>     the repository to look in (default: the current directory)
#   --path <path>    a path to check as given. Repeatable
#   <file>... | -    texts to scan: an issue body, an epic, a brief. "-" reads stdin
#
# A cited path is a word in backticks, or the target of a Markdown link, that looks like a file in
# the repository: it has a slash and a file extension, or ends in a slash, or is a top-level
# document such as README.md. A trailing :12 or #L12 is dropped. Commands, URLs, absolute paths,
# globs and placeholders are skipped.
#
# Prints OK or MISSING for each path, then a count. A missing path is fine only when the work
# itself will create that file. A document an agent is told to read must be on the ref first:
# a decision record left untracked in one checkout is in no worktree cut from the base.
#
# Exit codes: 0 every cited path is on the ref (or none is cited), 1 at least one is missing,
#             2 usage, or the ref or the repository cannot be read.
set -u
export LC_ALL=C

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
die2() { echo "cited-paths.sh: $*" >&2; exit 2; }

[ $# -ge 1 ] || usage
case $1 in -h | --help) usage ;; esac
ref=$1; shift
repo=.
paths=()
files=()
while [ $# -gt 0 ]; do
  case $1 in
    --repo) [ $# -ge 2 ] || die2 "--repo needs a directory"; repo=$2; shift 2 ;;
    --path) [ $# -ge 2 ] && [ -n "$2" ] || die2 "--path needs a path"; paths+=("$2"); shift 2 ;;
    -h | --help) usage ;;
    -) files+=(-); shift ;;
    -*) die2 "unknown option: $1" ;;
    *) files+=("$1"); shift ;;
  esac
done
[ ${#paths[@]} -gt 0 ] || [ ${#files[@]} -gt 0 ] || die2 "nothing to check: give a file, - for stdin, or --path"

git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || die2 "not a git repository: $repo"
git -C "$repo" rev-parse --verify --quiet "$ref^{commit}" >/dev/null \
  || die2 "no such ref in $repo: $ref (fetch first?)"
for f in "${files[@]+"${files[@]}"}"; do
  [ "$f" = - ] || [ -r "$f" ] || die2 "cannot read $f"
done

# Candidates: words in backticks and Markdown link targets, one per line, in order of appearance.
candidates() {
  local f
  for f in "${files[@]+"${files[@]}"}"; do
    if [ "$f" = - ]; then cat; else cat "$f"; fi
  done | tr -d '\r' | grep -oE '`[^` ]+`|\]\([^) ]+\)' | sed -e 's/^`//' -e 's/`$//' -e 's/^](//' -e 's/)$//'
}

# Keep what looks like a path in this repository, cleaned.
looks_like_path() {
  awk '
    { p = $0
      sub(/#.*$/, "", p)                       # an anchor or a #L12 line reference
      sub(/:[0-9]+(-[0-9]+)?$/, "", p)         # a :12 or :12-20 line reference
      sub(/[.,;:]+$/, "", p)                   # punctuation that followed the word
      sub(/^\.\//, "", p)
      if (p == "" || p ~ /^(\/|~|\.\.|-|@|\$|<)/) next
      if (p ~ /:\/\// || p ~ /[<>*{}$()=|"\\ ]/) next
      if (p ~ /\/$/) { print p; next }                                   # a directory
      if (p ~ /\// && p ~ /\.[A-Za-z0-9]+$/) { print p; next }           # dir/file.ext
      if (p ~ /^[A-Za-z0-9_.-]+\.(md|json|toml|yaml|yml|txt|lock)$/) print p   # a top-level document
    }'
}

list=$(
  { [ ${#files[@]} -eq 0 ] || candidates | looks_like_path
    [ ${#paths[@]} -eq 0 ] || printf '%s\n' "${paths[@]}"
  } | awk '!seen[$0]++'
)
if [ -z "$list" ]; then echo "no paths cited"; exit 0; fi

total=0 missing=0
while IFS= read -r p; do
  total=$((total + 1))
  if git -C "$repo" cat-file -e "$ref:${p%/}" 2>/dev/null; then
    echo "OK       $p"
  else
    echo "MISSING  $p"
    missing=$((missing + 1))
  fi
done <<<"$list"

echo "$total cited, $missing missing on $ref"
if [ "$missing" -gt 0 ]; then
  echo "A missing path is fine only when the work will create it. A document an agent is told to read must be on $ref first."
  exit 1
fi
exit 0
