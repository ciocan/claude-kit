#!/usr/bin/env bash
# Tests for cited-paths.sh. Everything runs in a throwaway git repository in a temp dir.
#
#   tests/cited-paths.sh      run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CP="$ROOT/plugins/flow/skills/grill-to-epic/scripts/cited-paths.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "  ok    $1"; }
no() { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/        /'; }
expect_code() { # name, wanted code, actual code, output
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (exit $3, wanted $2)" "$4"; fi
}
expect_has() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then ok "$1"; else no "$1 (missing: $2)" "$3"; fi
}
expect_not() { # name, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then no "$1 (found: $2)" "$3"; else ok "$1"; fi
}

# A repository with a base branch, and a decision record that exists only as an untracked file.
R="$T/repo"; mkdir -p "$R/docs/decisions" "$R/src"
g() { git -C "$R" -c user.name=test -c user.email=test@example.invalid -c commit.gpgsign=false "$@"; }
g init -q -b base
echo "# readme" >"$R/README.md"
echo "# old decision" >"$R/docs/decisions/0001-storage.md"
echo "export const a = 1" >"$R/src/app.ts"
g add -A; g commit -q -m "base"
echo "# the new record" >"$R/docs/prd-search.md"   # written after the grilling, never committed

cat >"$T/issue.md" <<'EOF'
## Context
Read `docs/prd-search.md` first, then the older [storage decision](docs/decisions/0001-storage.md).
The entry point is `src/app.ts:12`, see also `./README.md` and the `docs/decisions/` folder.

## Not paths
Run `bun run test`, call `users.setLocale`, branch `feat/12-search`, see https://example.com/a/b.md,
`/etc/hosts`, `~/notes/x.md`, `src/*.ts`, `<path>/file.md`, `$HOME/x.md`, `--flag=value/x.md`.

## Will be created
`src/search.ts`
EOF

echo "cited-paths.sh on an issue body"
out=$("$CP" base --repo "$R" "$T/issue.md" 2>&1); rc=$?
expect_code "a record that no ref holds fails the check" 1 "$rc" "$out"
expect_has "the untracked record is missing" "MISSING  docs/prd-search.md" "$out"
expect_has "a linked document is found" "OK       docs/decisions/0001-storage.md" "$out"
expect_has "a line reference is dropped" "OK       src/app.ts" "$out"
expect_has "a leading ./ is dropped" "OK       README.md" "$out"
expect_has "a folder is checked" "OK       docs/decisions/" "$out"
expect_has "a file the work will create is listed as missing" "MISSING  src/search.ts" "$out"
expect_has "the count" "6 cited, 2 missing on base" "$out"
expect_has "it says when a missing path is fine" "fine only when the work will create it" "$out"
for skip in "bun run test" "users.setLocale" "feat/12-search" "example.com" "/etc/hosts" "notes/x.md" "src/*.ts" "file.md" "HOME" "flag"; do
  expect_not "not a path: $skip" "$skip" "$out"
done

echo "cited-paths.sh once the record is on the base"
g add docs/prd-search.md; g commit -q -m "docs: the record"
out=$("$CP" base --repo "$R" --path docs/prd-search.md 2>&1); rc=$?
expect_code "an explicit path that is on the ref" 0 "$rc" "$out"
expect_has "it is found" "OK       docs/prd-search.md" "$out"
out=$("$CP" base --repo "$R" "$T/issue.md" 2>&1); rc=$?
expect_code "only the file to be created is still missing" 1 "$rc" "$out"
expect_has "the count went down" "6 cited, 1 missing on base" "$out"

echo "cited-paths.sh inputs"
out=$(printf 'Read `docs/prd-search.md` and `docs/nope.md`.\n' | "$CP" base --repo "$R" - 2>&1); rc=$?
expect_code "stdin" 1 "$rc" "$out"
expect_has "stdin: found" "OK       docs/prd-search.md" "$out"
expect_has "stdin: missing" "MISSING  docs/nope.md" "$out"
out=$(printf 'Read `docs/prd-search.md` twice: `docs/prd-search.md`.\r\n' | "$CP" base --repo "$R" - 2>&1); rc=$?
expect_code "a path cited twice, with CRLF line ends" 0 "$rc" "$out"
expect_has "it is counted once" "1 cited, 0 missing on base" "$out"
out=$(printf 'Nothing here but `a command`.\n' | "$CP" base --repo "$R" - 2>&1); rc=$?
expect_code "a text that cites nothing" 0 "$rc" "$out"
expect_has "it says so" "no paths cited" "$out"
out=$("$CP" base --repo "$R" --path "docs/a file with spaces.md" 2>&1); rc=$?
expect_code "an explicit path is checked as given" 1 "$rc" "$out"
expect_has "it is reported" "MISSING  docs/a file with spaces.md" "$out"

echo "cited-paths.sh usage"
out=$("$CP" 2>&1); rc=$?
expect_code "no ref is a usage error" 2 "$rc" "$out"
out=$("$CP" base --repo "$R" 2>&1); rc=$?
expect_code "nothing to check is a usage error" 2 "$rc" "$out"
out=$("$CP" nosuchref --repo "$R" --path README.md 2>&1); rc=$?
expect_code "an unknown ref is a usage error" 2 "$rc" "$out"
expect_has "it names the ref" "no such ref" "$out"
out=$("$CP" base --repo "$T" --path README.md 2>&1); rc=$?
expect_code "a folder that is not a repository is a usage error" 2 "$rc" "$out"
out=$("$CP" base --repo "$R" "$T/absent.md" 2>&1); rc=$?
expect_code "a file that cannot be read is a usage error" 2 "$rc" "$out"
out=$("$CP" base --repo "$R" --frob 2>&1); rc=$?
expect_code "an unknown option is a usage error" 2 "$rc" "$out"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
