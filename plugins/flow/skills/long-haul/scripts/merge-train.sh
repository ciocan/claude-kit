#!/usr/bin/env bash
# Merge pull requests in order without a human watching, and stop at the first doubt.
#
#   merge-train.sh [options] <pr> [<pr>...]
#
#   --repo <owner/repo>    default: the repository of the current directory
#   --method <m>           squash (default), merge or rebase
#   --dry-run              check everything, merge nothing
#   --poll <seconds>       wait between check polls (default 60)
#   --timeout-min <n>      how long to wait for one PR's checks (default 120)
#   --ignore-check <name>  a check to leave out of the verdict. Repeatable
#   --allow-no-checks      merge a PR that reports no checks at all
#   --delete-branch        delete the head branch after the merge
#   --after '<command>'    run after each merge with the PR number and merge commit as $1 and $2,
#                          for a deploy or a smoke. A failure stops the train
#
# For each PR: wait until every check settled, require OPEN, not a draft and MERGEABLE, merge
# with the head commit pinned, then confirm GitHub reports MERGED and the base branch moved.
#
# Lines to watch for: "MERGED #<pr>", "STOP ...", "ALL MERGED".
# Exit codes: 0 all merged, 1 stopped, 2 usage, 130 interrupted.
set -uo pipefail

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

repo=
method=squash
dry=
poll=60
timeout_min=120
allow_none=
delete_branch=
after=
ignore=()
while [ $# -gt 0 ]; do
  case $1 in
    --repo) repo=${2:-}; shift 2 || usage ;;
    --method) method=${2:-}; shift 2 || usage ;;
    --dry-run) dry=1; shift ;;
    --poll) poll=${2:-}; shift 2 || usage ;;
    --timeout-min) timeout_min=${2:-}; shift 2 || usage ;;
    --ignore-check) ignore+=("${2:-}"); shift 2 || usage ;;
    --allow-no-checks) allow_none=1; shift ;;
    --delete-branch) delete_branch=1; shift ;;
    --after) after=${2:-}; shift 2 || usage ;;
    -h | --help) usage ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) break ;;
  esac
done
case $method in squash | merge | rebase) ;; *) echo "--method must be squash, merge or rebase" >&2; exit 2 ;; esac
[ $# -ge 1 ] || usage
for tool in gh jq; do command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required" >&2; exit 2; }; done
[ -n "$repo" ] || repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || true
[ -n "$repo" ] || { echo "cannot tell the repository. Pass --repo <owner/repo>" >&2; exit 2; }

prs=("$@")
total=${#prs[@]}
ignore_json=$(printf '%s\n' "${ignore[@]+"${ignore[@]}"}" | jq -R . | jq -cs 'map(select(length > 0))')
ts() { date -u +%H:%M:%S; }
settle=${MERGE_TRAIN_SETTLE_S:-5}
i=0
pr=
merged=0
resume() { echo "Resume: $0 --repo $repo --method $method ${prs[*]:$i}"; }
stop() {
  echo "$(ts) STOP [$((i + 1))/$total] #$pr: $*. $merged merged so far."
  resume
  exit 1
}
trap 'echo; echo "$(ts) INTERRUPTED at #$pr, $merged merged so far."; resume; exit 130' INT TERM

echo "$(ts) merge train: $total PRs (${prs[*]}) in $repo, method $method, poll ${poll}s, timeout ${timeout_min} min${dry:+, dry run}"

for ((i = 0; i < total; i++)); do
  pr=${prs[$i]}
  tag="[$((i + 1))/$total] #$pr"

  # 1. Wait for the checks to settle.
  deadline=$(( $(date +%s) + timeout_min * 60 ))
  empty=0
  while :; do
    verdict=$(gh pr view "$pr" -R "$repo" --json statusCheckRollup 2>/dev/null | jq -r --argjson skip "$ignore_json" '
      [ .statusCheckRollup[]?
        | select(((.name // .context) as $n | $skip | index($n)) | not)
        | (if ((.conclusion // "") == "") then (.status // .state // "PENDING") else .conclusion end) ]
      | if length == 0 then "NONE"
        elif any(.[]; IN("FAILURE","ERROR","TIMED_OUT","CANCELLED","ACTION_REQUIRED","STARTUP_FAILURE","STALE")) then "FAILED " + (unique | join(","))
        elif any(.[]; IN("SUCCESS","NEUTRAL","SKIPPED") | not) then "PENDING " + (unique | join(","))
        else "GREEN " + (length | tostring) + " checks" end') || verdict="UNREADABLE"
    case $verdict in
      GREEN*) echo "$(ts) $tag checks: $verdict"; break ;;
      FAILED*) stop "a check did not pass ($verdict)" ;;
      NONE)
        if [ -n "$allow_none" ]; then echo "$(ts) $tag reports no checks, allowed"; break; fi
        empty=$((empty + 1))
        [ "$empty" -lt 4 ] || stop "no checks reported after $empty polls. Pass --allow-no-checks if this repository has none"
        ;;
      *) ;;
    esac
    [ "$(date +%s)" -lt "$deadline" ] || stop "checks did not settle within ${timeout_min} min (last: $verdict)"
    echo "$(ts) $tag waiting: $verdict"
    sleep "$poll"
  done

  # 2. The state must be settled and mergeable. UNKNOWN means GitHub is still computing.
  state= base= head= mergeable= draft=
  for ((t = 0; t < 20; t++)); do
    IFS=$'\t' read -r state base head mergeable draft < <(gh pr view "$pr" -R "$repo" \
      --json state,baseRefName,headRefOid,mergeable,isDraft \
      -q '[.state, .baseRefName, .headRefOid, .mergeable, (.isDraft | tostring)] | @tsv') || true
    [ "$mergeable" != UNKNOWN ] && [ -n "$mergeable" ] && break
    sleep "$settle"
  done
  [ "$state" = OPEN ] || stop "state is ${state:-unreadable}, expected OPEN"
  [ "$draft" = false ] || stop "it is a draft"
  [ "$mergeable" = MERGEABLE ] || stop "mergeable is ${mergeable:-unreadable}"
  before=$(gh api "repos/$repo/git/ref/heads/$base" -q .object.sha 2>/dev/null) || stop "cannot read $base"
  echo "$(ts) $tag head ${head:0:8} onto $base ${before:0:8}, --$method"
  if [ -n "$dry" ]; then
    echo "$(ts) $tag dry run, not merged"
    continue
  fi

  # 3. Merge with the head pinned, so a push that arrived meanwhile cannot ride along.
  gh pr merge "$pr" -R "$repo" "--$method" --match-head-commit "$head" ${delete_branch:+--delete-branch} \
    || stop "gh pr merge was refused"

  # 4. Believe only the MERGED state.
  oid=
  for ((t = 0; t < 12; t++)); do
    IFS=$'\t' read -r state oid < <(gh pr view "$pr" -R "$repo" --json state,mergeCommit \
      -q '[.state, (.mergeCommit.oid // "")] | @tsv') || true
    [ "$state" = MERGED ] && [ -n "$oid" ] && break
    sleep "$settle"
  done
  [ "$state" = MERGED ] || stop "GitHub does not report MERGED after the merge call (state ${state:-unreadable})"
  now=$(gh api "repos/$repo/git/ref/heads/$base" -q .object.sha 2>/dev/null) || now=
  [ -n "$now" ] && [ "$now" != "$before" ] || stop "merged as ${oid:0:8}, but $base did not move"
  merged=$((merged + 1))
  echo "$(ts) MERGED #$pr as ${oid:0:8} [$merged/$total]"
  if [ "$method" = squash ]; then
    parent=$(gh api "repos/$repo/commits/$oid" -q '.parents[0].sha' 2>/dev/null) || parent=
    if [ "$parent" != "$before" ]; then
      i=$((i + 1))
      stop "it merged, but $base moved under it (${before:0:8} became ${parent:0:8}). Look before going on"
    fi
  fi

  # 5. What the merge owes: deploy, smoke.
  if [ -n "$after" ]; then
    echo "$(ts) $tag after-merge: $after"
    if ! bash -o pipefail -c "$after" _ "$pr" "$oid"; then
      i=$((i + 1))
      stop "the after-merge command failed for #$pr, which is merged"
    fi
  fi
done

if [ -n "$dry" ]; then
  echo "$(ts) dry run finished: $total PRs checked, none merged"
else
  echo "$(ts) ALL MERGED: $merged of $total"
fi
