# Keeping going

How a session carries work across hours with nobody at the keyboard, and what it has to rebuild
after a restart. Product facts here come from the Claude Code documentation as read on
2026-11-17 ([goal](https://code.claude.com/docs/en/goal),
[scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks)). Check them against your
version.

## What survives what

| Thing | After the session exits and is resumed | Note |
|---|---|---|
| The active goal | restored | The turn count and timer reset. An error the user must fix (login, full disk, credits, context overflow) clears it |
| Fixed-schedule tasks (`/loop 30m ...`, a scheduled one-shot) | restored unless expired | Recurring ones expire after seven days. Missed fires are not caught up. They fire only while the session runs and is idle |
| A self-paced loop (`/loop <prompt>`) | not restored | Start it again |
| Background commands and watchers | not restarted | They are cleaned up when the session exits |
| Subagents | resumable with SendMessage while their transcript exists | A stopped agent does not resume by itself |
| Detached processes (`run-detached.sh`, tmux) | still running | The session does not track them. Watch their log |
| Cloud scheduled tasks | independent of any session | They start from a fresh clone with no local files, and run at most hourly |

The machine has to stay on. A background session survives a closed terminal, not a reboot.

## The goal

- The condition is checked after every turn by a small model that sees the conversation only. It
  runs nothing and opens nothing. Make each check print its result.
- While a subagent or a background command runs, the check is deferred. Check-ins come after 30
  minutes, then an hour, then every two hours, and after three of them with no word from the user
  they pause. A goal alone does not carry a session through a night of waiting.
- A detached job is invisible to the goal. Give it a watcher or a scheduled check.
- Several turns in a row without a tool call stop the loop. When everything waits on the user,
  end the turn by scheduling the next check, not by saying "still waiting".
- A usage limit pauses the goal. It continues when the window resets if the session is left
  waiting, or on the user's "continue".
- A goal does not change the permission mode. Unattended turns need auto mode.
- To bound a run, put the bound in the condition: "or stop after 40 turns".

## Wake-ups

Pick the delay from what you are waiting for.

| Waiting for | Delay used |
|---|---|
| A watcher is the real signal, this is the fallback | about 25 minutes |
| Reviews, merges or CI in motion | 30 minutes |
| Everything is blocked on the user | 60 minutes |
| A usage window to reset | to land a minute or two after the reset |

State the reason in one line: the signal you rely on, what is in flight, what is blocked and on
whom, the next event you expect.

A scheduled follow-up that must survive a compaction carries everything in its own text:

```text
Scheduled follow-up (set <YYYY-MM-DD HH:MM UTC>, goal <goal or issue #n>).
Context: <one sentence on what was running and why this check exists>. Baseline: <numbers>.
Check, read-only: <exact commands> in <absolute path>. Not allowed: <what to leave alone>.
Expect: <the exact success condition>.
If it holds: run <exact command> from <absolute path>, expect <output>, then confirm <condition>.
If it does not hold: change nothing. <Report to the user | push a notification>.
Record: a comment on <issue #n> and a line in <the program note>.
If <precondition> has not happened yet: say so, change nothing, schedule this same text again
<interval> later.
```

Schedule off the hour and the half hour. A one-shot task on those minutes runs up to 90 seconds
early.

## Watchers

Three forms. Give each a timeout of about 30 minutes and arm it again when it ends.

```bash
# Stream: one line per milestone or failure of a log.
touch <log>; tail -n 0 -F <log> | grep -a --line-buffered -E '== <name> exit |FAILED|STOP|DONE'

# Finite: ends by itself when the run ends or dies. Uses the pid file, never pgrep.
log=<log>; pidf=<pid file>
while :; do
  m=$(grep -a -F "== <name> exit " "$log" | tail -n 1); [ -n "$m" ] && { echo "$m"; break; }
  [ -f "$pidf" ] && ! kill -0 "$(cat "$pidf")" 2>/dev/null && { echo "<name> is gone, no exit line"; break; }
  sleep 60
done

# GitHub: one line per settled check, ends when none is pending.
prev=; while :; do
  s=$(gh pr checks <pr> --json name,bucket 2>/dev/null) || { sleep 60; continue; }
  cur=$(jq -r '.[] | select(.bucket != "pending") | "\(.name): \(.bucket)"' <<<"$s" | sort)
  comm -13 <(echo "$prev") <(echo "$cur"); prev=$cur
  jq -e 'length > 0 and all(.bucket != "pending")' <<<"$s" >/dev/null && { echo "checks settled"; break; }
  sleep 90
done
```

- `touch` the log first, so the watcher can follow a file that does not exist yet.
- `tail -n 0` misses a line written before the watcher started. Read the log once after arming.
- `-F`, not `-f`. A log that is recreated is lost with `-f`.
- Match markers, not words. `error|skip|start` wakes the session for nothing.
- `pgrep -f <name>` inside a watcher matches the watcher's own command line. It never reports
  "gone".

## Scripts

Four scripts ship in this skill's `scripts/` directory. Copy them into the repository (a
`scripts/` or `tools/` folder, never the scratchpad) so they outlive the session and the plugin
version. `tests/long-haul.sh` in the kit's repository exercises all four.

**`run-detached.sh <name> [--dir <dir>] -- <command>`** starts a command that survives the
session. The log's last line is `== <name> exit <rc>`. `touch <dir>/<name>.stop` ends it,
children included. A second start under the same name is refused.

**`after.sh <name> [--dir <dir>] -- <follow-up>`** runs the follow-up only after that marker says
exit 0. A failed run, a run that died without a marker, and a missed deadline each stop with their
own line and exit code. Waiting only for "the process is gone" runs the follow-up after a failure.

**`chain.sh <steps file> [--dir <dir>] [--from <step>] [--dry-run]`** runs named steps in order,
each into its own log, with `pipefail` on, and stops at the first failure. `STATUS` holds the
latest line. The failure line gives the command that resumes. Write each guard as its own step:

```text
guard-disk	[ "$(df --output=avail -BG / | tail -n 1 | tr -dc 0-9)" -ge 150 ]
guard-build	test "$(deployed-build)" = "$(git rev-parse --short origin/main)"
migrate	./migrate.sh apply
rebuild	./rebuild.sh --all
verify	./check.sh
```

For a night: `run-detached.sh night -- chain.sh night.tsv`, then a watcher on
`== night exit |FAILED|STOP`.

**`merge-train.sh [options] <pr>...`** merges PRs in order. For each one it waits until every
check has settled, requires an open, non-draft, mergeable PR, merges with the head commit pinned,
and believes only GitHub's `MERGED` state and a base branch that moved. `--after '<command>'`
runs the deploy or smoke the merge owes. It stops at the first doubt with the command that
resumes. `--dry-run` checks everything and merges nothing. When the permission system will not
let the session merge, hand the same command to the user (`owner-scripts`).

Rules the scripts encode, for the ones you write yourself:

- Take the exit code from the command, never from a pipe into `tail` or `grep`.
- A wait has a deadline and stops the chain when it gives up. A wait that times out and carries
  on anyway hides the failure it was guarding against.
- A chain that was killed leaves no failure line. The watcher on the pid file catches that.
- Two tags for the same commit can differ in length. Compare prefixes when a guard checks a build.
- A go-file (`while [ ! -f GO ]; do sleep 120; done`) lets a chain wait for a human step.

## Notifications

Push to the user's phone in three cases only: they must act, a result they are waiting for has
arrived, or a resource alarm threatens running work (and once more when it clears). Never for a
routine merge.

Under about 200 characters: the repository, the state with numbers, the one command or script
path, the deadline if there is one, and what you did or did not touch.

> PR #412 is green. Merge and deploy: bash /abs/path/merge-412-owner.sh

> 108 GB free, the 88 GB floor is about 80 min away. I have not touched it.

Phone pushes need Remote Control to be connected.

## Permissions while unattended

- Auto mode refuses some actions by default, among them production deploys and migrations, force
  pushes, and merging a PR nobody approved. What a given setup allows is the user's decision, in
  their own settings.
- Three refusals in a row, or twenty in a session, pause auto mode and the session goes back to
  asking. Record a refused step in the paste file and move on. Retrying it ends the night.

## Usage

- An interactive session signed in with a subscription waits at a usage limit and continues by
  itself after the reset. That is the default.
- Check before each wave with `npx -y ccusage@latest blocks --active --json`. The status line's
  input carries the five-hour and seven-day percentages as well.
- Other sessions spend the same windows. Plan for a share.
