#!/usr/bin/env bash
# Set up Claude Code on a new machine: this kit's two plugins, the third-party plugins and skills
# it leans on, and the global instruction block. Dry run by default. --apply acts.
#
# Safe to run twice: a step whose result is already present is skipped.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(dirname "$HERE")"
MANIFEST="$HERE/manifest.json"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LOG="${TMPDIR:-/tmp}/claude-kit-install.$(date +%Y%m%d-%H%M%S).log"
BLOCK_START='<!-- claude-kit:start (managed by claude-kit bootstrap/install.sh) -->'
BLOCK_END='<!-- claude-kit:end -->'

APPLY=0
PROFILE=minimal
KIT_SOURCE="$KIT"
SKIP=""

usage() {
  cat <<'USAGE'
Usage: install.sh [--apply] [--profile minimal|full] [--kit-source <path|owner/repo>]
                  [--skip kit|unslop|plugins|skills|claude-md]...

  --apply        act. Without it the script prints what it would do and changes nothing.
  --profile      minimal (default): what the flow plugin leans on.
                 full: every plugin and skill in manifest.json.
  --kit-source   where Claude Code loads this kit from. Default: this checkout.
                 Use owner/repo once the kit is on GitHub.
  --skip         leave a group of steps out. Repeatable.

Exit codes: 0 done, 1 a step failed, 2 not configured, 130 interrupted.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --profile) PROFILE="${2:-}"; shift ;;
    --kit-source) KIT_SOURCE="${2:-}"; shift ;;
    --skip) SKIP="$SKIP ${2:-}"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$PROFILE" in
  minimal | full) ;;
  *) echo "--profile must be minimal or full" >&2; exit 2 ;;
esac
skipped() { case " $SKIP " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

missing=""
for tool in claude jq git npx; do
  command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
if [ -n "$missing" ]; then
  echo "missing tools:$missing. Install them and run again." >&2
  exit 2
fi
[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 2; }

MARKETPLACES="$(claude plugin marketplace list 2>/dev/null || true)"
have_marketplace() { printf '%s\n' "$MARKETPLACES" | grep -qE "(^|[[:space:]])$1\$"; }
have_plugin() {
  jq -e --arg k "$1" '.plugins[$k]' "$CLAUDE_DIR/plugins/installed_plugins.json" >/dev/null 2>&1
}
have_skill() { [ -e "$CLAUDE_DIR/skills/$1" ]; }

# The step list: "label<TAB>command" per line. Steps already satisfied are counted, not listed.
STEPS="$(mktemp)"
trap 'rm -f "$STEPS"' EXIT
SATISFIED=0
add() { printf '%s\t%s\n' "$1" "$2" >>"$STEPS"; }
q() { printf '%q' "$1"; }

if ! skipped kit; then
  if have_marketplace claude-kit; then
    SATISFIED=$((SATISFIED + 1))
  else
    add "add marketplace claude-kit" "claude plugin marketplace add $(q "$KIT_SOURCE")"
  fi
  for p in flow@claude-kit unslop@claude-kit; do
    # A machine that already has the unslop skill and hook installed by hand skips the plugin,
    # or every prompt gets the reminder twice.
    if [ "$p" = unslop@claude-kit ] && skipped unslop; then
      continue
    fi
    if have_plugin "$p"; then
      SATISFIED=$((SATISFIED + 1))
    else
      add "install plugin $p" "claude plugin install $(q "$p")"
    fi
  done
fi

if ! skipped plugins; then
  while IFS=$'\t' read -r name source; do
    if have_marketplace "$name"; then
      SATISFIED=$((SATISFIED + 1))
    else
      add "add marketplace $name" "claude plugin marketplace add $(q "$source")"
    fi
  done < <(jq -r --arg p "$PROFILE" '.marketplaces[$p][] | [.name, .source] | @tsv' "$MANIFEST")
  while IFS= read -r p; do
    if have_plugin "$p"; then
      SATISFIED=$((SATISFIED + 1))
    else
      add "install plugin $p" "claude plugin install $(q "$p")"
    fi
  done < <(jq -r --arg p "$PROFILE" '.plugins[$p][]' "$MANIFEST")
fi

if ! skipped skills; then
  while IFS=$'\t' read -r via source name; do
    if have_skill "$name"; then
      SATISFIED=$((SATISFIED + 1))
      continue
    fi
    case "$via" in
      agent-native)
        add "install skill $name" "npx -y @agent-native/skills@latest add --skill $(q "$name")"
        ;;
      agent-native-core)
        add "install skill $name" "npx -y @agent-native/core@latest skills add $(q "$name")"
        ;;
      skills-cli)
        add "install skill $name from $source" \
          "npx -y skills add $(q "$source") -g -a claude-code -s $(q "$name") -y"
        ;;
      *) echo "manifest: unknown install method '$via' for $name" >&2; exit 2 ;;
    esac
  done < <(jq -r --arg p "$PROFILE" \
    '.skills[$p][] | . as $g | .names[] | [$g.via, ($g.source // "-"), .] | @tsv' "$MANIFEST")
fi

CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
CLAUDE_MD_STEP=0
if ! skipped claude-md; then
  wanted="$(printf '%s\n' "$BLOCK_START"; cat "$HERE/CLAUDE.global.md"; printf '%s\n' "$BLOCK_END")"
  current=""
  if [ -f "$CLAUDE_MD" ]; then
    current="$(awk -v s="$BLOCK_START" -v e="$BLOCK_END" \
      '$0==s{on=1} on{print} $0==e{on=0}' "$CLAUDE_MD")"
  fi
  if [ "$current" = "$wanted" ]; then
    SATISFIED=$((SATISFIED + 1))
  else
    CLAUDE_MD_STEP=1
  fi
fi

write_claude_md() {
  mkdir -p "$CLAUDE_DIR"
  local tmp
  tmp="$(mktemp)"
  if [ -f "$CLAUDE_MD" ]; then
    cp "$CLAUDE_MD" "$CLAUDE_MD.bak-$(date +%Y%m%d-%H%M%S)"
    # Keep everything outside the managed block.
    awk -v s="$BLOCK_START" -v e="$BLOCK_END" \
      '$0==s{on=1; next} $0==e{on=0; next} !on{print}' "$CLAUDE_MD" >"$tmp"
    [ -s "$tmp" ] && printf '\n' >>"$tmp"
  fi
  {
    printf '%s\n' "$BLOCK_START"
    cat "$HERE/CLAUDE.global.md"
    printf '%s\n' "$BLOCK_END"
  } >>"$tmp"
  mv "$tmp" "$CLAUDE_MD"
}

TOTAL=$(($(wc -l <"$STEPS") + CLAUDE_MD_STEP))
MODE="dry run, nothing will change"
[ "$APPLY" = 1 ] && MODE="applying, log at $LOG"
echo "claude-kit install: profile $PROFILE, $TOTAL steps to run, $SATISFIED already in place, $MODE" >&2

if [ "$TOTAL" = 0 ]; then
  echo "nothing to do" >&2
  exit 0
fi

OK=0
FAILED=0
I=0
trap 'echo >&2; echo "interrupted at step $I of $TOTAL ($OK ok, $FAILED failed). Run the same command again, finished steps are skipped." >&2; rm -f "$STEPS"; exit 130' INT

while IFS=$'\t' read -r label cmd <&3; do
  I=$((I + 1))
  if [ "$APPLY" != 1 ]; then
    printf '[%d/%d] %s\n        %s\n' "$I" "$TOTAL" "$label" "$cmd" >&2
    continue
  fi
  started=$(date +%s)
  printf '[%d/%d] %s ... ' "$I" "$TOTAL" "$label" >&2
  printf '\n=== [%d/%d] %s\n$ %s\n' "$I" "$TOTAL" "$label" "$cmd" >>"$LOG"
  if bash -c "$cmd" >>"$LOG" 2>&1 </dev/null; then
    OK=$((OK + 1))
    printf 'ok (%ds)  [%d ok, %d failed]\n' "$(($(date +%s) - started))" "$OK" "$FAILED" >&2
  else
    FAILED=$((FAILED + 1))
    printf 'FAILED (%ds)  [%d ok, %d failed]\n' "$(($(date +%s) - started))" "$OK" "$FAILED" >&2
  fi
done 3<"$STEPS"

if [ "$CLAUDE_MD_STEP" = 1 ]; then
  I=$((I + 1))
  if [ "$APPLY" != 1 ]; then
    printf '[%d/%d] write the managed block in %s\n        from %s, the rest of the file is kept, a backup is made\n' \
      "$I" "$TOTAL" "$CLAUDE_MD" "$HERE/CLAUDE.global.md" >&2
  else
    printf '[%d/%d] write the managed block in %s ... ' "$I" "$TOTAL" "$CLAUDE_MD" >&2
    if write_claude_md >>"$LOG" 2>&1; then
      OK=$((OK + 1))
      printf 'ok  [%d ok, %d failed]\n' "$OK" "$FAILED" >&2
    else
      FAILED=$((FAILED + 1))
      printf 'FAILED  [%d ok, %d failed]\n' "$OK" "$FAILED" >&2
    fi
  fi
fi

if [ "$APPLY" != 1 ]; then
  echo "dry run finished. Run again with --apply to act." >&2
  exit 0
fi

echo "done: $OK ok, $FAILED failed, $SATISFIED were already in place. Log: $LOG" >&2
echo "Restart Claude Code, or run /reload-plugins, to load what was installed." >&2
[ "$FAILED" = 0 ] || exit 1
