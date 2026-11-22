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
Kept by the user: <decision classes, for example money, legal text, privacy, security, production>.
Refused to me, do not retry: <commands>. They go to the paste file.
User-only steps: <list>. Paste file: <path>.

Holds: no merge <window or condition>. Nothing starts below <n> GB free disk, <n> GB free memory.
Peers: <session, what it holds, how to reach it>. Claims folder: <path>.
Shared in this run: <what the worktrees share and the guard on each, see `orchestrate`>.
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
- Ruling (<user | session>): <question>, <what was chosen>, <how to overrule it>
- Next: <three steps at most>
- Correction: the <time> entry said <x>, it is <y>
```

Append it with the script, one argument per bullet. The script writes the heading:

```sh
note.py add <note file> "Landed: #412 (#398), merge 1a2b3c4" "Next: review of #413"
```

Write one at every merge, launch, hand-back, failure, and before every compaction. Before a
compaction the entry must hold everything a successor needs to restart: agent ids with their
worktrees, each watcher and what it does when it fires, each chain with its resume command.

## Rules that keep the note readable

- Times in UTC, in order, taken from the machine. `note.py` does that. Never type a time. On one
  64-hour run the session wrote times from memory: the note ran up to 15 hours ahead of the
  tracker, went backwards three times, and no duration in it could be trusted.
- Correct an earlier line with a `Correction` bullet in a new entry. Do not rewrite history, and
  do not leave the wrong line standing alone.
- No shorthand without its meaning on first use in each rotated file. "Paste 26" and "r736" mean
  nothing to the next session.
- A background task id is never the only handle on a job. Give the log path and the command.
- State goes in the log. Lessons go in their own notes with a link. Commands for the user go in
  the paste file.

## Rotation

Rotate when the log passes about 300 lines, when a phase ends, or once a day on a busy run.
`note.py add` warns at 300 lines. One note that relied on the rule alone reached 4,913.

1. Move the log to `goal-<slug>-log-<yyyy-mm-dd>.md`.
2. In the main note leave five lines: what that period achieved, what it left open, the file name.
3. Carry forward anything still live: running jobs, agents, holds, what the user owes.

`note.py rotate` does the three steps and leaves the top block untouched:

```sh
note.py rotate <note file> --summary "Phase 2 merged, 14 pull requests" \
  --summary "Open: the audit of #420" --carry "Running: reindex, log /abs/reindex.log"
```

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
7. Check the holds: peers' windows and claims, production schedules, disk and memory floors,
   usage.
8. Note which pastes are still outstanding and whether the user answered since.
9. Re-measure every claim about deployed state before you repeat it, and give the time you
   measured. "Five pull requests are not live on the dev backend" was told to a user for hours
   after it had stopped being true.
10. Run `note.py check`. Then write one "re-anchored" entry with `note.py add`, and act.

The first briefs after a compaction need more care than the rest: re-read the decisions they rest
on. In one run four of eleven context-loss incidents fell within two hours of a compaction, among
them a brief that contradicted a recorded decision.

When the log, the repository and this note disagree, `git log` and GitHub are right, then the
log, then the top block.
