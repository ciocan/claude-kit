#!/usr/bin/env bash
# Record what each session has deployed to a shared resource, so sessions that cannot message
# each other can still see it before they push.
#
#   claims.sh claim   <resource> <ref> [note...] [--owner <label>] [--dir <dir>]
#   claims.sh release <resource> [--owner <label>] [--dir <dir>]
#   claims.sh list    [<resource>] [--dir <dir>]
#   claims.sh check   <resource> [--owner <label>] [--dir <dir>]
#
# A claim says "this session has deployed <ref> to <resource>". Several owners may hold claims on
# one resource at once. Before a push, run check: it lists the other owners' claims, and you push
# the union of their refs and yours, or wait. Each claim is one file, <dir>/<resource>/<owner>.claim.
# Claiming again replaces your own claim. Resource and owner use letters, digits, dot, dash and
# underscore. The ref is free text on one line: a branch, a sha, a PR.
#
# Env: CLAIMS_OWNER, else LOCK_OWNER, is the label when --owner is absent. CLAIMS_DIR is the folder
# (default $XDG_STATE_HOME/claude-kit/claims, else ~/.local/state/claude-kit/claims). Keep it
# outside any repository, so every worktree and session reads the same claims.
#
# Exit codes: 0 ok or clear, 1 others hold a claim (check only), 2 usage.
set -u
shopt -s nullglob dotglob

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
die() { echo "claims.sh: $*" >&2; exit 2; }

[ $# -ge 1 ] || usage
cmd=$1; shift
case $cmd in claim | release | list | check) ;; *) usage ;; esac

state=${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}
dir=${CLAIMS_DIR:-${state:+$state/claude-kit/claims}}
owner=${CLAIMS_OWNER:-${LOCK_OWNER:-}}
owner_given=
pos=()
while [ $# -gt 0 ]; do
  case $1 in
    --owner) [ $# -ge 2 ] || usage; owner=$2; owner_given=1; shift 2 ;;
    --dir) [ $# -ge 2 ] || usage; dir=$2; shift 2 ;;
    --) shift; pos+=("$@"); break ;;
    -h | --help | --*) usage ;;
    *) pos+=("$1"); shift ;;
  esac
done

valid() { [[ $1 =~ ^[A-Za-z0-9._-]+$ ]] && [ "$1" != . ] && [ "$1" != .. ]; }
need_resource() {
  valid "$1" || die "bad resource name '$1': use letters, digits, dot, dash, underscore"
}
need_owner() {
  [ -n "$owner" ] || die "an owner label is required: pass --owner <label> or set CLAIMS_OWNER
(or LOCK_OWNER). Every command runs in a new shell, so only the label tells your claim apart."
  valid "$owner" || die "bad owner label '$owner': use letters, digits, dot, dash, underscore"
}

case $cmd in
  claim) [ ${#pos[@]} -ge 2 ] || usage ;;
  release | check) [ ${#pos[@]} -eq 1 ] || usage ;;
  list)
    [ ${#pos[@]} -le 1 ] || usage
    [ -z "$owner_given" ] || die "list takes no --owner" ;;
esac
[ ${#pos[@]} -eq 0 ] || need_resource "${pos[0]}"
[ "$cmd" = list ] || need_owner
[ -n "$dir" ] || die "no claims folder: set CLAIMS_DIR or HOME, or pass --dir"
mkdir -p "$dir" || die "cannot create the claims folder $dir"

age() { # seconds as a short readable age
  local s=$1
  [ "$s" -ge 0 ] || s=0
  if [ "$s" -lt 60 ]; then echo "${s}s"
  elif [ "$s" -lt 3600 ]; then echo "$((s / 60))m"
  elif [ "$s" -lt 86400 ]; then echo "$((s / 3600))h $((s % 3600 / 60))m"
  else echo "$((s / 86400))d $((s % 86400 / 3600))h"; fi
}

rows() { # claim files, printed one per line, oldest first
  local f line r o ref t e n now a
  now=$(date +%s)
  for f in "$@"; do
    ref= t= e= n=
    while IFS= read -r line || [ -n "$line" ]; do
      case $line in
        ref=*) ref=${line#ref=} ;;
        time=*) t=${line#time=} ;;
        epoch=*) e=${line#epoch=} ;;
        note=*) n=${line#note=} ;;
      esac
    done <"$f"
    # The path is what check and release go by, so the names come from it.
    o=${f##*/}; o=${o%.claim}
    r=${f%/*}; r=${r##*/}
    a="age unknown"
    if [[ $e =~ ^[0-9]+$ ]]; then a=$(age $((now - e))); else e=0; fi
    printf '%s\t%s  %s  %s  %s  %s  %s\n' "$e" "$r" "$o" "${ref:--}" "${t:-unknown}" "$a" "${n:--}"
  done | sort -t "$(printf '\t')" -k1,1n -k2 | cut -f2-
}

res=${pos[0]:-}
case $cmd in
  claim)
    ref=${pos[1]}
    [ -n "$ref" ] || die "the ref is empty"
    [[ $ref != *$'\n'* ]] || die "the ref must be one line"
    note="${pos[*]:2}"
    note=${note//$'\n'/ }
    d=$dir/$res
    mkdir -p "$d" || die "cannot create $d"
    t=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    tmp=$d/.$owner.claim.tmp.$$.$RANDOM
    if ! printf 'owner=%s\nresource=%s\nref=%s\ntime=%s\nepoch=%s\nhost=%s\nnote=%s\n' \
      "$owner" "$res" "$ref" "$t" "$(date +%s)" \
      "${HOSTNAME:-$(hostname 2>/dev/null || echo unknown)}" "$note" >"$tmp" ||
      ! mv -f "$tmp" "$d/$owner.claim"; then
      rm -f "$tmp"
      die "cannot write the claim in $d"
    fi
    echo "CLAIMED $res for $owner at $t: $ref" ;;
  release)
    f=$dir/$res/$owner.claim
    if [ -e "$f" ]; then
      rm -f "$f" || die "cannot remove $f"
      echo "RELEASED $res for $owner"
    else
      echo "NO CLAIM $res for $owner"
    fi ;;
  list)
    if [ -n "$res" ]; then files=("$dir/$res"/*.claim); else files=("$dir"/*/*.claim); fi
    if [ ${#files[@]} -eq 0 ]; then
      if [ -n "$res" ]; then echo "no claims on $res"; else echo "no claims"; fi
    else
      rows "${files[@]}"
    fi ;;
  check)
    others=()
    for f in "$dir/$res"/*.claim; do
      [ "${f##*/}" = "$owner.claim" ] || others+=("$f")
    done
    if [ ${#others[@]} -eq 0 ]; then
      echo "CLEAR $res: no other claims"
      exit 0
    fi
    rows "${others[@]}"
    echo "OTHERS HOLD $res: push the union of these refs and yours, or wait"
    exit 1 ;;
esac
exit 0
