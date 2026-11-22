# Brief for the evidence agent

Fill in the angle brackets. Keep it neutral: no claim to confirm, no verdict asked. The agent
builds an inventory. The judgement is yours.

```
Read-only evidence pass over one orchestrator session of <repo>: <session id>, <start> to <end>
UTC. Change nothing: no edits, commits, comments, labels, runs or deploys. `gh` reads only.

## Sources, in this order of trust
1. The tracker: `gh pr view`, `gh issue view`, `gh run list`. Every time and every count that
   exists there comes from there.
2. The transcript digest: <path>, made by transcript-digest.py. Its timestamps are the
   transcript's. The raw transcript is <path>, for searching.
3. The session's notes: <paths>. They say what the session believed. Where a note's time
   differs from the tracker's, give both and use the tracker's.
4. <PRD, epic, decisions log, memory notes>.

Read the digest in full. If it is too long for one read, split it into overlapping ranges, give
each to a read-only sub-reader with this same class list, and reopen yourself every item that
carries weight.

## A. Incidents, one table per class
Each row: when (UTC), what happened, what it cost (time, reruns, wrong data, money), who or what
caught it, the reference (a digest line, a note line, a tracker link).

1. Shared-resource collision: two agents or sessions on one database, backend, account,
   sandbox, runner, port, host, branch or file.
2. Context loss: the session acted on something stale, forgotten or never read. Give the gap to
   the nearest compaction before it, and say when there was none.
3. Wrong decision: a ruling or a plan that was later reversed or corrected. By whom.
4. Defect merged and found later: what, which merge carried it, when found, how long it lived,
   severity, whether it reached production, who found it and how.
5. Defect caught before merge: counts per pull request by round, then the five most serious.
6. Agent misbehaviour: a false report, a skipped step, work outside the brief, an early exit, a
   refused action attempted another way.
7. Other: CI, tools, the host, hooks.

## B. Production actions   [only when the run touched production]
Every action that changed production or could have, in time order: the action, the user's words
that authorised it quoted exactly with their time, and whether the words came before or after
the action. List separately what the session declined or left for the user.

## C. Mechanisms that held
Locks, checks, save-and-restore routines, kill switches, permission refusals, agents that
stopped instead of guessing, notes that let work resume. A count and the three clearest cases
for each.

## D. Decisions
How many were the user's and how many the session's, and how you can tell. Which of the
session's touched money, security, privacy, legal text or production. Which were later found
wrong.

## E. Numbers
Pull requests merged with lines changed, issues closed, launches by role, fix rounds per pull
request, CI reruns and their causes, compactions, completion prompts from hooks or goal checks,
permission refusals.

## F. Could not determine, and contradictions
What the sources do not settle. Where two sources disagree, quote both.

## Rules
- Every row carries a reference you opened. No reference, no row.
- "Cannot tell" is an answer. Never guess a cause or an owner.
- Report what happened. Do not rank the session, do not recommend changes.
- Write the inventory to <path outside the repository> and give a ten-line summary as your
  final message.
```

Check the user's messages before you send the brief: run the digest script with
`--user-messages` and read the list. If a message you remember is missing, the digest is
incomplete and the authority table will be wrong.
