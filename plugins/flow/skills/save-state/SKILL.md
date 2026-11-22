---
name: save-state
description: Write the session's working state to durable notes so the work survives context compaction, a restart or a new session, and answer whether it is safe to compact. Use when the user asks "can I compact this session?", "is everything important written down?" or "make sure to write this to memory", before an unattended run, after each merge or agent launch in an orchestrated epic, and when the user states a rule or grants a permission that must outlive the conversation.
---

# Save state

## Where state lives

- The project's memory directory holds the state of an epic or a goal, the user's rules and their
  grants.
- The repository holds what other people need: decisions in the docs, progress as comments on the
  epic issue.
- The scratchpad holds nothing that matters for more than an hour. It can be emptied by an agent,
  and on many hosts it is RAM.

When a ledger or the git history disagrees with a memory note, the ledger and git win.

## A document written for the repository

A decision record, a handoff, a report, a record of rounds, a script for the user: anything the
session writes that belongs in the repository and is not part of a slice.

- Write it in a worktree, on a branch of its own cut from the integration branch. Never in the
  user's checkout, unless they asked for the edit there ("work here").
- With a commit grant: commit it and land it as its own small pull request (`ship-pr`).
- Under a no-commit rule: stage it on that branch, write the commit message, and give the user one
  command, listed under what they owe. An untracked file that "lands later" is not a state to
  leave. One session left a decision record untracked in the user's checkout, the user committed
  it by hand, and the session then moved the file, which deleted a tracked file from their tree.
- Before you move or edit it later, look at who holds it now: `git log -1 -- <path>` on the base,
  `git status` in the worktree. The user may have committed it since.

## Three kinds of note

Templates for all three are in [references/templates.md](references/templates.md).

1. **State note**, one per epic or goal. It opens with the fixed facts (the epic, the delivery
   shape, who implements and who verifies) and continues as a log with a timestamp on every entry.
   Append at each merge, launch and hand-back.
2. **Rule or grant note**, one per thing the user said. Quote their words exactly, with the date
   and time. Record what it covers, what it does not, and whether it ends (one night, one epic,
   until revoked). Label your own reading of an unclear word as yours.
3. **Decision note**, one per round of decisions. Each question, the option chosen, what follows
   from it, and a tag that says whose decision it was: the user's or the session's.

Keep grants and state in separate notes. A grant that grows a state log becomes unreadable.

## What not to save

What the repository already records: code structure, merged work, commit history. Summaries of
finished work. Anything that only matters inside this conversation.

## "Can I compact?"

Answer in this order:

1. Yes or no.
2. What is saved and where, by file name.
3. What would be lost. Say "nothing" only after checking the list below.
4. What must be restarted afterwards, with the commands.

Check before answering:

- every agent in flight is in the state note with its id, worktree and branch, so it can be
  resumed with SendMessage
- background jobs are listed with their log paths and the command that resumes them
- the user's rules and grants from this session each have a note
- the queue and the next step are written down
- commands the user still owes are listed in order

Processes started by this session (watchers, merge queues, monitors) do not survive a restart.
Record how to start them again.

## After compaction or in a new session

Read the tail of the state note, the epic issue, `git log` and `gh pr list`. Restart the monitors.
Then continue from the first item that has no landed PR.

## Handing over to a fresh session

When the context is nearly full, or the next stage belongs to another session, agent or machine,
write two things:

1. A handoff document in the repository, written and landed as above: what was decided and why,
   what is done, what is next, the traps met so far.
2. A prompt to paste into the new session. It names the document to read first, the stage to do,
   the points where it must stop and smoke test, and the standing rules, for example "do not
   commit, I review after each stage".

For staged work write one prompt per stage. The user pastes the next one after reviewing the
last. A message to another agent or machine has the same shape: what happened, what it owns,
what it must leave alone.

## Work that runs for weeks

A goal that outlasts a session gets a program note with a top block edited in place and a log
that is rotated. The template, the log entry and the re-anchor checklist are in `long-haul`, with
`note.sh`, which stamps each entry from the machine and rotates the log. Use it for a state note
too once the log is long: `note.sh add <note> "<bullet>"`.

For a program that spans several repositories, also keep a ledger outside the memory directory:
one folder per day, one line per merged PR. Reconcile it against
`gh pr list --state merged --search "merged:>=<date>"` in each repository before saying it is up
to date. Take dates from the machine.
