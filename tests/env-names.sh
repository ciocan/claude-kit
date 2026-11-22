#!/usr/bin/env bash
# Tests for env-names.py. The point of the script is what it never prints, so most checks here
# are that a piece of a value is absent from the output.
#
#   tests/env-names.sh        run everything
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EN="$ROOT/plugins/flow/skills/start/scripts/env-names.py"
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
expect_eq() { # name, wanted, actual
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (got '$3', wanted '$2')"; fi
}
run() { python3 -B "$EN" "$@" 2>&1; }

W="$T/work"; mkdir -p "$W"
# Every value below is invented. The key block has the shape that leaked through a line grep:
# continuation lines that start with letters and digits.
cat >"$W/.env" <<'EOF'
# a comment with NOT_A_NAME=1 inside
DATABASE_URL=postgres://user:hunter2@db.example.invalid/app
export AUTH_SECRET="s3cr3tvalue"
PRIVATE_KEY="-----BEGIN KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASC
Qk1hZA==
INNER_LOOKS_LIKE=an_assignment
-----END KEY-----"
PAYMENT_KEY='sk_test_abc123'
JSON_BLOB='{
  "client_email": "robot@example.invalid",
  "token": "ZmFrZXRva2Vu"
}'
ESCAPED="line one \" still open
STILL_INSIDE=yes
closed here"
  SPACED_NAME = value with spaces
EMPTY=
DATABASE_URL=again
9BAD=not a name
EOF

echo "env-names.py on a file with values that run over several lines"
out=$( cd "$W" && run ); rc=$?
expect_code "it runs" 0 "$rc" "$out"
expect_eq "the names, in order, each once" ".env: DATABASE_URL AUTH_SECRET PRIVATE_KEY PAYMENT_KEY JSON_BLOB ESCAPED SPACED_NAME EMPTY" "$out"
for piece in hunter2 s3cr3tvalue MIIEvQ Qk1hZA INNER_LOOKS_LIKE an_assignment "BEGIN KEY" sk_test client_email robot ZmFrZXRva2Vu "line one" STILL_INSIDE "closed here" "value with spaces" again NOT_A_NAME 9BAD postgres; do
  expect_not "no piece of a value or a comment: $piece" "$piece" "$out"
done

echo "env-names.py and a plain line grep, for comparison"
# What a grep for the word at the start of each line prints on the same file: this is the leak.
leak=$( cd "$W" && grep -ho '^[A-Za-z_][A-Za-z0-9_]*' .env | sort -u | tr '\n' ' ' )
expect_has "the grep prints a line of the key" "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" "$leak"
expect_not "the script does not" "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" "$out"

echo "env-names.py inputs"
printf 'A=1\r\nB="two"\r\n' >"$W/.env.local"
printf '# nothing here\n\n' >"$W/.env.empty"
out=$( cd "$W" && run ); rc=$?
expect_code "several files" 0 "$rc" "$out"
expect_has "CRLF line ends" ".env.local: A B" "$out"
expect_has "a file with no variables" ".env.empty: (no variables)" "$out"
expect_has "the first file is still listed" ".env: DATABASE_URL" "$out"
out=$( cd "$W" && run .env.local ); rc=$?
expect_eq "a named file only" ".env.local: A B" "$out"
printf 'OPEN="never closed\nSECRET_TAIL_LINE\n' >"$W/.env.open"
out=$( cd "$W" && run .env.open ); rc=$?
expect_eq "a quote that never closes hides the rest" ".env.open: OPEN" "$out"
printf 'ONE="a"\nTWO="b"\n' >"$W/.env.next"
out=$( cd "$W" && run .env.open .env.next ); rc=$?
expect_has "an open quote does not carry into the next file" ".env.next: ONE TWO" "$out"
echo "env-names.py and a quote that opens inside a value"
cat >"$W/.env.mid" <<'EOF'
TOKEN=prefix"first line
SECRET_FRAGMENT=more of the value
"
AFTER_MID=1
TWO_QUOTES="closed" then 'open again
HIDDEN_PIECE=still inside
' and "a third
THIRD_PIECE=inside too
"
WITH_COMMENT=value # it's a comment, the apostrophe opens nothing
AFTER_COMMENT=2
ESCAPED_QUOTE=one\"two
AFTER_ESCAPE=3
HASH_IN_VALUE=abc#"not a comment
PIECE_AFTER_HASH=inside
"
LAST=4
EOF
out=$( cd "$W" && run .env.mid ); rc=$?
expect_eq "names only, with quotes opening mid-value" ".env.mid: TOKEN AFTER_MID TWO_QUOTES WITH_COMMENT AFTER_COMMENT ESCAPED_QUOTE AFTER_ESCAPE HASH_IN_VALUE LAST" "$out"
for piece in SECRET_FRAGMENT HIDDEN_PIECE THIRD_PIECE PIECE_AFTER_HASH "first line" "more of" "still inside"; do
  expect_not "no piece of a value: $piece" "$piece" "$out"
done

echo "env-names.py on forms other programs accept"
# Each block is a value that runs over several lines in a form the first version did not track.
cat >"$W/.env.forms" <<'EOF'
FIRST=1
PRIVATE_KEY: "-----BEGIN KEY-----
MIIEvQIBADANBgColonForm
Zk9xQwErTy1=
-----END KEY-----"
SECOND=2
firebase.key="-----BEGIN KEY-----
AbCdEfSecret=
-----END KEY-----"
THIRD=3
UNQUOTED_KEY=-----BEGIN KEY-----
MIIEunquotedBlock=
Proc-Type: 4,ENCRYPTED
-----END KEY-----
FOURTH=4
PASS='it\'s
MIIEsecretTail==
EOF
out=$( cd "$W" && run .env.forms ); rc=$?
expect_code "it runs" 0 "$rc" "$out"
for name in FIRST PRIVATE_KEY SECOND firebase.key THIRD UNQUOTED_KEY FOURTH PASS; do
  expect_has "a real name is listed: $name" " $name" "$out"
done
for piece in MIIEvQIBADANBgColonForm Zk9xQwErTy1 AbCdEfSecret MIIEunquotedBlock Proc-Type MIIEsecretTail "BEGIN" "END"; do
  expect_not "no piece of a value: $piece" "$piece" "$out"
done
# Where the two readings of a single quote differ, later lines stay hidden under the reading
# that keeps the quote open. A name may go missing. Nothing leaks.
printf "A='x\\\\'\nB=after\nC='end'\nD=last\n" >"$W/.env.readings"
out=$( cd "$W" && run .env.readings ); rc=$?
expect_has "the name before the doubtful quote is listed" ".env.readings: A" "$out"
expect_not "no value under either reading" "after" "$out"

echo "env-names.py and a value carried on by a backslash"
# In a shell a backslash at the end of a line joins the next line to the value.
printf 'BEFORE=1\nTOKEN=prefix\\\nc2VjcmV0==\nMORE=part\\\nTAILPIECE=x\\\nLASTPIECE=y\nAFTER=2\nPLAIN=one\nNEXT=two\nCOMMENTED=v # ends with a backslash \\\nSEEN=3\n' >"$W/.env.cont"
out=$( cd "$W" && run .env.cont ); rc=$?
expect_eq "names only, with values carried over lines" ".env.cont: BEFORE TOKEN MORE AFTER PLAIN NEXT COMMENTED SEEN" "$out"
for piece in c2VjcmV0 TAILPIECE LASTPIECE; do
  expect_not "no piece of a carried value: $piece" "$piece" "$out"
done

mkdir -p "$T/none"
out=$( cd "$T/none" && run ); rc=$?
expect_code "no env file at all" 0 "$rc" "$out"
expect_has "it says so" "no .env files here" "$out"
out=$( cd "$W" && run .env.absent ); rc=$?
expect_code "a named file that cannot be read" 2 "$rc" "$out"
expect_has "it names the file" "cannot read .env.absent" "$out"

[ -z "$(find "$ROOT/plugins/flow/skills/start" -name __pycache__)" ] && ok "no __pycache__ left behind" || no "no __pycache__ left behind"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
