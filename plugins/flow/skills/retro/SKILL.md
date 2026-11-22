---
name: retro
description: Run a retrospective of one or more long orchestrated sessions from the transcripts and the tracker, not from the session's own notes. Count compactions, agent launches and the user's messages, send one evidence agent with a neutral brief and fixed incident classes, reopen the most serious items, then report against the claims being tested and list what to change. Use when the user says "do a retro on the X sessions", "do the same for the other session", "how much of these concerns are valid", "what went wrong in that run", or wants to learn from a finished epic or goal.
---

# Retro

A retrospective answers a claim with counts: "worktrees are not enough isolation", "nobody reads
the diff", "long sessions lose the thread". It is read-only. It changes no code and no note.

## 1. Count from the record, not from the notes

The session's own notes are evidence about the notes. One program note ran up to 15 hours ahead
of the tracker, so no duration in it could be used.

- **Transcripts.** One JSONL file per session under `~/.claude/projects/<path slug>/`. Find the
  sessions by date and size, and confirm each with the user.
- **`scripts/transcript-digest.py <session.jsonl>`** prints the span, each compaction with its
  token count before it, agent launches by role and model, and the user's messages. `--out`
  writes a chronological digest for the evidence agent. `--user-messages` lists every message
  counted as the user's. A person reads that list before any authorisation is quoted from it.
  `--json` gives the counts for a table across sessions.
- **Queued messages.** What the user types while the session is busy is stored as a queue
  record, not as a user message. A first digest that missed them lost 13 of 25 messages, among
  them every authorisation given that night. The script reads both. A message the user pulled
  back from the queue before it was delivered is not counted, and the digest marks it withdrawn.
- **Answers to questions.** When the session asked with a question dialog, the user's choice is
  stored as a tool result. So are the words a user types when rejecting a question or a tool
  call. The script lists both as an `answer` next to the typed messages.
- **Typed is not always the user.** A line another session types into this session's pane is
  stored as the user's own. Before an authorisation goes in the table, check who wrote it.
- **The tracker.** Merge and close times, pull requests, lines changed, CI runs and reruns come
  from `gh`, never from the note.

## 2. One evidence agent, neutral brief

Send one agent to build the inventory. Its brief asks for no verdict and gives no hypothesis: an
agent handed a conclusion returns it confirmed. The template is in
[references/evidence-brief.md](references/evidence-brief.md). It fixes:

- seven incident classes: shared-resource collision, context loss (with the gap to the nearest
  compaction), wrong decision, defect merged and found later, defect caught before merge, agent
  misbehaviour, other
- mechanisms that held, with counts
- decisions by who took them: the user or the session
- for a run that touched production, every production action next to the words that authorised
  it, and which came first

A long digest is read in overlapping ranges by sub-readers. The evidence agent reopens by hand
the items that carry weight.

## 3. Reopen the worst yourself

Before reporting, open the source lines for the most serious items: each production action, each
defect that reached users, each claim about who authorised what. A count you did not check is
reported as the agent's count.

## 4. Report

1. The claims being tested, each with a verdict and the figures behind it: valid, partly valid,
   not supported.
2. What held, so the fix does not remove a guard that worked.
3. What to change, ranked. Prefer a script or a check to a new sentence. In two retrospectives
   the rules already written down were broken on a long run, and the locks, the read-back
   checks and the kill switch held.
4. What could not be determined, and where the sources contradict each other.

## Rules

- A retrospective of a private project stays private. When a lesson moves into a shared skill,
  write what happened, the figure and the guard, with no name, number or quoted sentence that
  identifies the project.
- Quote the user's authorising words exactly, with the time from the transcript.
- Several sessions get the same brief and the same classes, so their tables can sit side by
  side.
- Keep the evidence files outside the repository, next to the session's other working files.
