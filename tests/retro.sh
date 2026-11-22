#!/usr/bin/env bash
# Tests for the retro scripts. transcript-digest.py runs against hand-written transcripts with
# invented content: tests/fixtures/retro-session.jsonl holds one record of every shape the script
# reads, tests/fixtures/retro-queue.jsonl the harder queue cases (shell commands, withdrawn
# messages, harness text that passes through the queue).
#
#   tests/retro.sh            run everything
#   RETRO_DIGEST=copy.py tests/retro.sh
#                             run the same checks against another copy of the script
#
# Exit code: 0 all passed, 1 at least one failed.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/plugins/flow/skills/retro/scripts"
F="$ROOT/tests/fixtures/retro-session.jsonl"
Q="$ROOT/tests/fixtures/retro-queue.jsonl"
DIGEST="${RETRO_DIGEST:-$S/transcript-digest.py}"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export PYTHONDONTWRITEBYTECODE=1
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
  if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (got $3, wanted $2)"; fi
}
jget() { # json text, python expression over d. The expressions are written in this file only.
  printf '%s' "$1" | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1]), sort_keys=True))' "$2" 2>&1
}
# -B: running the script must leave no __pycache__ in the repository.
digest() { python3 -B "$DIGEST" "$@" 2>&1; }

echo "transcript-digest.py: counts"
J=$(digest --json "$F"); rc=$?
expect_code "--json runs" 0 "$rc" "$J"
expect_eq "span starts at the first timestamp" '"2026-01-10T10:00:00.000Z"' "$(jget "$J" "d['span']['first']")"
expect_eq "span ends at the last timestamp" '"2026-01-10T11:31:00.000Z"' "$(jget "$J" "d['span']['last']")"
expect_eq "one broken line is counted as unparsed" 1 "$(jget "$J" "d['unparsed_lines']")"
expect_eq "the sidechain record is skipped" 1 "$(jget "$J" "d['sidechain_records_skipped']")"
expect_eq "two compactions" 2 "$(jget "$J" "len(d['compactions'])")"
expect_eq "pre-compaction token counts" '[175500, 180000]' "$(jget "$J" "sorted(c['pre_tokens'] for c in d['compactions'])")"
expect_eq "compaction timestamp and trigger" '["2026-01-10T11:30:00.000Z", "manual"]' "$(jget "$J" "[d['compactions'][1]['timestamp'], d['compactions'][1]['trigger']]")"
expect_eq "one compaction summary" 1 "$(jget "$J" "d['compaction_summaries']")"
expect_eq "answers to questions, counted apart from messages" '[2, 1]' "$(jget "$J" "[d['answers_to_questions'], d['questions_declined']]")"
expect_eq "user messages in total" 12 "$(jget "$J" "d['user_messages']['total']")"
expect_eq "typed messages" 7 "$(jget "$J" "d['user_messages']['typed']")"
expect_eq "queued messages" 5 "$(jget "$J" "d['user_messages']['queued']")"
expect_eq "slash commands" 2 "$(jget "$J" "d['user_messages']['slash_commands']")"
expect_eq "shell commands" 1 "$(jget "$J" "d['user_messages']['shell_commands']")"
expect_eq "sightings merged by the dedupe" 3 "$(jget "$J" "d['user_messages']['duplicates_merged']")"
expect_eq "launches in total" 5 "$(jget "$J" "d['launches']['total']")"
expect_eq "launches by role and model" \
  '{"(default)": {"(inherit)": 1}, "flow:implementer": {"opus": 2}, "flow:reviewer": {"sonnet": 1}, "flow:verifier": {"opus": 1}}' \
  "$(jget "$J" "d['launches']['by_role']")"
expect_eq "messages sent to running agents" 1 "$(jget "$J" "d['agent_messages_sent']")"
expect_eq "questions put to the user" 3 "$(jget "$J" "d['questions_to_user']")"
expect_eq "tool errors" 4 "$(jget "$J" "d['tool_errors']")"
expect_eq "permission denials by kind" '{"by_kind": {"permission-rule": 1, "user-rejected": 2}, "total": 3}' "$(jget "$J" "d['permission_denials']")"
expect_eq "stop-hook prompts" 2 "$(jget "$J" "d['stop_hook_prompts']")"
expect_eq "goal checks" '{"feedback": 1, "notifications": 1}' "$(jget "$J" "d['goal_checks']")"
expect_eq "interrupts" 1 "$(jget "$J" "d['interrupts']")"
expect_eq "assistant turns count message ids, not records" 6 "$(jget "$J" "d['assistant_turns']")"
expect_eq "context median and max" '[21005, 40005]' "$(jget "$J" "[d['context_median'], d['context_max']]")"
expect_eq "output tokens are counted once per turn" 620 "$(jget "$J" "d['output_tokens']")"
expect_eq "harness lines in user records, by kind" \
  '{"agents-stopped": 1, "goal-check": 1, "interrupt": 1, "local-command-output": 1, "peer-session": 1, "scheduled": 1, "shell-output": 1, "stop-hook": 2, "system-reminder": 1, "task-notification": 2}' \
  "$(jget "$J" "d['system_lines']")"
expect_eq "harness lines in the queue, by kind" \
  '{"agent-message": 1, "agents-stopped": 1, "task-notification": 1}' "$(jget "$J" "d['queued_system_lines']")"

echo "transcript-digest.py: dedupe"
J0=$(digest --json --dedupe-seconds 0 "$F")
expect_eq "--dedupe-seconds 0 turns merging off" 15 "$(jget "$J0" "d['user_messages']['total']")"
expect_eq "with merging off every queue sighting counts" 8 "$(jget "$J0" "d['user_messages']['queued']")"
expect_eq "with merging off nothing is merged" 0 "$(jget "$J0" "d['user_messages']['duplicates_merged']")"
J9=$(digest --json --dedupe-seconds 600 "$F")
expect_eq "a wider window merges the late re-delivery too" 11 "$(jget "$J9" "d['user_messages']['total']")"

echo "transcript-digest.py: --user-messages"
L=$(digest --user-messages "$F"); rc=$?
expect_code "--user-messages runs" 0 "$rc" "$L"
expect_eq "one line per typed or queued message" 12 "$(printf '%s\n' "$L" | grep -cE "$(printf '\t(typed|queued)\t')")"
expect_eq "one line per answered question" 2 "$(printf '%s\n' "$L" | grep -c "$(printf '\tanswer\t')")"
expect_has "an answer is listed with its time and kind" "$(printf '2026-01-10T10:42:00.000Z\tanswer\tAfter review')" "$L"
expect_has "an answer in the older result shape is listed" "$(printf '2026-01-10T10:42:40.000Z\tanswer\tmain')" "$L"
expect_not "a declined question is not listed as an answer" "Delete the old tags" "$L"
expect_has "a typed message, tab separated" "$(printf '2026-01-10T10:00:00.000Z\ttyped\tfix the login redirect')" "$L"
expect_has "a message queued and absorbed mid-turn" "$(printf '2026-01-10T10:05:00.000Z\tqueued\tok release then')" "$L"
expect_eq "absorbed message listed once" 1 "$(printf '%s\n' "$L" | grep -c 'ok release then')"
expect_eq "re-delivery inside the window listed once" 1 "$(printf '%s\n' "$L" | grep -c 'also bump')"
expect_eq "re-delivery outside the window listed twice" 2 "$(printf '%s\n' "$L" | grep -c 'check the staging logs')"
expect_eq "the same words typed twice count twice" 2 "$(printf '%s\n' "$L" | grep -c 'status?')"
expect_has "a slash command shows as typed" "$(printf 'typed\t/flow:start the login epic')" "$L"
expect_has "a shell command shows with its bang" "$(printf 'typed\t!git status')" "$L"
expect_has "an image-only queued message is the user's" "$(printf '2026-01-10T10:50:00.000Z\tqueued\t[image]')" "$L"
expect_has "newlines become spaces" "$(printf 'typed\tlooks good, merge it')" "$L"
for h in "background agents were stopped" "Stop hook feedback" "Goal check-in" "Request interrupted" \
  "local-command-stdout" "system-reminder" "Another Claude session" "task-notification" \
  "agent-message" "nightly link check" "bash-stdout" "continued from a previous" \
  "a line from inside an agent" "Set model to sonnet"; do
  expect_not "harness line is not the user's: $h" "$h" "$L"
done

echo "transcript-digest.py: text output and --out"
D="$T/digest.md"
out=$(digest "$F" --out "$D"); rc=$?
expect_code "text mode with --out runs" 0 "$rc" "$out"
expect_has "text names the user messages" "user messages: 12 (typed 7, queued while busy 5" "$out"
expect_has "text gives the unparsed lines" "unparsed lines: 1" "$out"
expect_has "text lists a compaction" "preTokens=180000  trigger=auto" "$out"
expect_has "text lists launches by role and model" "flow:implementer on opus: 2" "$out"
dg=$(cat "$D" 2>/dev/null)
expect_has "digest marks a compaction" "COMPACTION preTokens=175500 trigger=manual" "$dg"
expect_has "digest marks a queued message" "USER (queued while busy): ok release then" "$dg"
expect_has "digest marks a typed message" "USER (typed): fix the login redirect" "$dg"
expect_has "digest shows a launch" "LAUNCH flow:reviewer sonnet: Review redirect fix" "$dg"
expect_has "digest shows an agent report" "AGENT REPORT: <task-notification>" "$dg"
expect_has "digest shows a harness line as system" "SYSTEM agents-stopped: 2 background agents" "$dg"
expect_has "digest shows a denial" "DENIED (permission-rule)" "$dg"
expect_has "digest shows a message to an agent" "SEND TO reviewer" "$dg"
expect_has "digest shows a question to the user" "ASKED THE USER" "$dg"
expect_has "digest shows the answer with its time" '[01-10T10:42] USER ANSWERED: "Release now or after review?" = "After review"; "Who reviews it?" = "The second reviewer"' "$dg"
expect_has "digest shows an answer in the older result shape" '[01-10T10:42] USER ANSWERED: "Which branch?"="main".' "$dg"
expect_has "digest shows a declined question" "[01-10T10:42] USER DECLINED THE QUESTION (user-rejected)" "$dg"
expect_has "text gives the answers" "answers to questions: 2, declined: 1" "$out"
expect_eq "digest shows the agent report once" 1 "$(grep -c 'AGENT REPORT: <task-notification>' "$D")"

echo "transcript-digest.py: the queue"
JQ=$(digest --json "$Q"); rc=$?
expect_code "--json on the queue fixture runs" 0 "$rc" "$JQ"
LQ=$(digest --user-messages "$Q")
expect_eq "queue fixture: user messages in total" 9 "$(jget "$JQ" "d['user_messages']['total']")"
expect_eq "queue fixture: typed and queued" '[2, 7]' "$(jget "$JQ" "[d['user_messages']['typed'], d['user_messages']['queued']]")"
expect_eq "a queued shell command counts once" 1 "$(printf '%s\n' "$LQ" | grep -c 'npm run lint')"
expect_has "a queued shell command shows with its bang" "$(printf '2026-02-03T09:00:00.000Z\tqueued\t!npm run lint')" "$LQ"
expect_eq "queue fixture: shell commands" 2 "$(jget "$JQ" "d['user_messages']['shell_commands']")"
expect_eq "a queued message that starts with a bang is not a shell command, and counts once" 1 "$(printf '%s\n' "$LQ" | grep -c 'just loud')"
expect_eq "a shell command delivered after the window still counts once" 1 "$(printf '%s\n' "$LQ" | grep -c 'make docs')"
expect_eq "queue fixture: late merges" 1 "$(jget "$JQ" "d['user_messages']['late_merges']")"
expect_not "a message pulled back from the queue is not listed" "ship it to production" "$LQ"
expect_has "its replacement is listed" "$(printf 'queued\tship it to staging only')" "$LQ"
expect_not "every message of a joined popAll is withdrawn" "then restart" "$LQ"
expect_eq "a withdrawn message typed again counts once" 1 "$(printf '%s\n' "$LQ" | grep -c 'run the migration')"
expect_eq "withdrawals are counted" 5 "$(jget "$JQ" "d['user_messages']['withdrawn']")"
expect_eq "the same text queued twice, one delivered and one pulled back, counts once" 1 "$(printf '%s\n' "$LQ" | grep -c 'yes, go ahead')"
expect_has "the delivered one keeps its own time" "$(printf '2026-02-03T12:00:00.000Z\tqueued\tyes, go ahead')" "$LQ"
expect_eq "the same with the remove before the attachment" 1 "$(printf '%s\n' "$LQ" | grep -c 'hold the release')"
expect_eq "a typed message repeating a queued one counts twice" 2 "$(printf '%s\n' "$LQ" | grep -c 'deploy the docs site')"
for h in "Autonomous loop tick" "Autonomous loop check" "usage limit has reset" "Background agent" \
  "Nightly report" "Wake up and look"; do
  expect_not "harness text from the queue is not the user's: $h" "$h" "$LQ"
done
expect_eq "harness lines in the queue, by kind" \
  '{"agents-stopped": 1, "loop": 2, "meta": 1, "scheduled": 1, "usage-limit-reset": 1}' "$(jget "$JQ" "d['queued_system_lines']")"
out=$(digest "$Q" --out "$T/queue.md")
expect_has "text gives the withdrawals" "withdrawn from the queue: 5" "$out"
dq=$(cat "$T/queue.md" 2>/dev/null)
expect_has "digest shows a withdrawal with its time" "[02-03T09:40] WITHDRAWN FROM THE QUEUE (queued 02-03T09:40): ship it to production" "$dq"
expect_not "digest does not show a withdrawn message as sent" "USER (queued while busy): ship it to production" "$dq"
expect_has "digest shows moved harness text as system" "SYSTEM meta (queued): Nightly report" "$dq"
expect_not "digest does not show moved harness text as the user's" "USER (queued while busy): Nightly report" "$dq"

echo "transcript-digest.py: edge cases"
out=$(digest "$T/missing.jsonl"); rc=$?
expect_code "a missing file exits 2" 2 "$rc" "$out"
expect_has "it says which file" "cannot read $T/missing.jsonl" "$out"
: >"$T/empty.jsonl"
JE=$(digest --json "$T/empty.jsonl"); rc=$?
expect_code "an empty transcript exits 0" 0 "$rc" "$JE"
expect_eq "an empty transcript has zero counts" '[0, 0, 0, 0, 0]' \
  "$(jget "$JE" "[d['records'], d['user_messages']['total'], len(d['compactions']), d['launches']['total'], d['unparsed_lines']]")"
out=$(digest "$T/empty.jsonl"); rc=$?
expect_code "an empty transcript in text mode exits 0" 0 "$rc" "$out"
printf 'not json\n{"type":"user","timestamp":"2026-01-10T09:00:00.000Z","origin":{"kind":"human"},"promptSource":"typed","message":{"content":"hello"}}\n[1, 2]\n' >"$T/junk.jsonl"
JJ=$(digest --json "$T/junk.jsonl")
expect_eq "non-JSON and non-object lines are unparsed" 2 "$(jget "$JJ" "d['unparsed_lines']")"
expect_eq "the good line still counts" 1 "$(jget "$JJ" "d['user_messages']['total']")"
printf '%s\n' '{"type":"user","message":"hi"}' \
  '{"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":null}]}}' \
  '{"type":"assistant","message":{"id":"m2","usage":{"input_tokens":"5"},"content":[]}}' \
  '{"type":"system","subtype":"compact_boundary","compactMetadata":"x"}' \
  '{"type":"user","timestamp":"2026-01-10T09:00:00.000Z","origin":{"kind":"human"},"promptSource":"typed","message":{"content":"still here"}}' >"$T/odd.jsonl"
out=$(digest "$T/odd.jsonl"); rc=$?
expect_code "records of an unexpected shape do not end the run" 0 "$rc" "$out"
expect_not "no traceback" "Traceback" "$out"
expect_has "text gives the malformed records" "malformed records: 4" "$out"
JO=$(digest --json "$T/odd.jsonl")
expect_eq "malformed records are counted apart from unparsed lines" '[4, 0]' "$(jget "$JO" "[d['malformed_records'], d['unparsed_lines']]")"
expect_eq "the good record after them still counts" 1 "$(jget "$JO" "d['user_messages']['total']")"
out=$(digest --json --user-messages "$F"); rc=$?
expect_code "--json and --user-messages together are a usage error" 2 "$rc" "$out"

if find "$ROOT" -name __pycache__ -path '*retro*' | grep -q .; then no "no __pycache__ left in the retro skill"; else ok "no __pycache__ left in the retro skill"; fi

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
