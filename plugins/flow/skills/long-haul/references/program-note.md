# The program note

One note per goal, in the project's memory directory. It has a top block that is edited in place
and a log that is only appended to.

## Top block

```markdown
---
name: goal-<slug>
description: "<RUNNING | WAITING ON USER: what | DONE yyyy-mm-dd>: <one line on where it stands>"
metadata:
  type: project
---

STATUS: <RUNNING | WAITING ON USER: <what> | DONE <date time UTC>>

Goal (user's words, <date time UTC>): "<the /goal text, verbatim>"
Amendments: <date time>: "<verbatim>", which changed <what in done or scope>
Definition of done:
1. <check>, proven by <command or figure>
2. <check>, proven by <command or figure>
Evidence is posted on: <issue or comment>
My readings, not the user's words: <reading>. Confirm by <when>.

Scope: epic #<n>, slices #<a> to #<b>. Out of scope: <list>.
Phases: 1 <name> [done] · 2 <name> [running] · 3 <name> [blocked by <x>]

Standing grants: "<quote>" (<date>). Covers <list>.
Refused to me, do not retry: <commands>. They go to the paste file.
User-only steps: <list>. Paste file: <path>.

Holds: no merge <window or condition>. Nothing starts below <n> GB free disk, <n> GB free memory.
Peers: <session, what it holds, how to reach it>.
Usage: at most <n> agents, <model per role>, throttle at <rule>.

Log: below, rotated to <path pattern>. Lessons: [[<note>]]. Follow-ups: <label or note>.
```

Edit the `STATUS` line and the frontmatter description when the state changes. A note whose
description still says "running" a week after the goal was met sends the next session to work.

## Log entry

```markdown
## <yyyy-mm-dd hh:mm UTC>
- Landed: #<pr> (#<issue>), merge <sha>, deployed to <where>
- Running: <job>, log <path>, <n> of <N>, <rate>, ETA <time>. Watcher fires on "<log line>"
- Agents: <role>, #<issue>, <agent id>, <worktree>, <branch>, <round or state>
- Holds: <what is held, until which message or time>
- User owes: <numbered paste lines or decisions>, asked at <time>
- Next: <three steps at most>
- Correction: the <time> entry said <x>, it is <y>
```

Write one at every merge, launch, hand-back, failure, and before every compaction. Before a
compaction the entry must hold everything a successor needs to restart: agent ids with their
worktrees, each watcher and what it does when it fires, each chain with its resume command.

## Rules that keep the note readable

- Times in UTC, in order, taken from the machine.
- Correct an earlier line with a `Correction` bullet in a new entry. Do not rewrite history, and
  do not leave the wrong line standing alone.
- No shorthand without its meaning on first use in each rotated file. "Paste 26" and "r736" mean
  nothing to the next session.
- A background task id is never the only handle on a job. Give the log path and the command.
- State goes in the log. Lessons go in their own notes with a link. Commands for the user go in
  the paste file.

## Rotation

Rotate when the log passes about 300 lines, when a phase ends, or once a day on a busy run.

1. Move the log to `goal-<slug>-log-<yyyy-mm-dd>.md`.
2. In the main note leave five lines: what that period achieved, what it left open, the file name.
3. Carry forward anything still live: running jobs, agents, holds, what the user owes.

## The paste file

`<topic>-pastes.md`, numbered lines, one command each, in the order they must run. Each line has
the expected duration and what its last output line should say. Mark a line done with the time it
ran. See `owner-scripts`.

## Re-anchor checklist

Run this after every restart, resume or compaction, before anything else.

1. Read the top block: status, goal, definition of done, grants, holds.
2. Read the last log entry, and the paste file.
3. `git fetch`, compare the main branch with the last recorded commit, list open PRs and their CI.
4. For every job the log calls running: is it alive, and what does the last line of its log say?
5. Start again what died with the old session: watchers, the merge train, the periodic wake-up.
6. List worktrees and agents. Resume agents with SendMessage where they can be resumed. Send a
   fresh agent, pointed at the work on disk, where they cannot.
7. Check the holds: peers' windows, production schedules, disk and memory floors, usage.
8. Note which pastes are still outstanding and whether the user answered since.
9. Write one "re-anchored" entry. Then act.

When the log, the repository and this note disagree, `git log` and GitHub are right, then the
log, then the top block.
