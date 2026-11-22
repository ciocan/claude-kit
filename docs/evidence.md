# Evidence

The numbers at the top of the README, with what each one counts and what it cannot tell apart.
Measured on 17 November 2026 between 22:43 and 22:58 UTC, on the two machines I used Claude Code
on. A sample was then recounted independently: the prompt history of one machine, the pull
requests of three repositories and the agent launches matched exactly.

## The window

The first prompt I typed to Claude Code is dated 3 April 2026 on the first machine. I moved most
work to a second machine on 31 July. Six repositories moved with me. The rest exist on one
machine only. Every combined figure below counts a pull request, an issue, a commit, a session
and a note once, whichever machine it was seen on.

## The numbers

| Figure | Value | What it counts |
|---|---|---|
| Repositories | 39 | GitHub repositories that have a checkout on either machine and at least one prompt in Claude Code's history. 31 private, 8 public |
| Pull requests merged | 2,188 | Authored by my GitHub account and merged after the first prompt I typed in that repository |
| The same, wider | 2,395 | Authored by my account and merged in those repositories since 3 April, including the ones merged before Claude was first used there |
| Naming Claude | 2,139 of the 2,395 | The pull request body or one of its commit messages mentions Claude Code or carries a Claude co-author trailer |
| Commits co-authored by Claude | 8,444 | Distinct commits on any ref of the local clones, dated in the window, with a `Co-Authored-By: Claude` trailer. Out of 13,596 commits by anyone |
| Issues closed | 1,805 | Closed in those repositories since 3 April, by anyone. 2,664 were opened |
| Prompts | 12,418 | Lines in Claude Code's prompt history on both machines: 6,189 and 6,229 |
| Sessions | 1,010 | Distinct session ids. Two sessions were resumed across the move and are counted once |
| Days | 185 | Calendar days in UTC with at least one prompt, out of 229 in the window |
| Agents launched | 2,621 | Calls to the agent tool in the transcripts still on disk on one machine, each call counted once by its id. Old transcripts are deleted after about a month, so this covers events from 22 September, mostly sessions active since 24 October |
| Memory notes | 462 | Notes Claude kept per project, distinct across machines. 89 of them record a correction or a trap |

## What the prompts asked for

Counted by pattern over the 12,418 prompts. These measure wording, not intent.

| Pattern | Prompts |
|---|---|
| Sending an agent ("deploy an agent", "dispatch agents", misspellings included) | 379 |
| Mentioning a smoke test | 331 |
| Opening a design grilling | 114 |
| Setting a `/goal` | 59 |
| Going to sleep or to bed | 35 |

## What the numbers cannot tell apart

- A pull request counts as mine by its author login. That does not prove it was made on either
  machine or with Claude. The 2,139 figure shows only that Claude is named.
- Pull requests opened by release tooling and dependency bots (380) and by other people (310) are
  left out of every figure.
- Commit counts come from local clones that were not fetched first. They are lower bounds.
- The agent count covers one machine and only the transcripts that were still there.
- Private repositories are counted and not named.

## What went wrong on two long runs

Counted in November 2026, after the numbers above. Two orchestrated sessions that used this
kit were taken apart afterwards with the `retro` skill: one evidence agent per session, a neutral
brief, fixed classes, times from the tracker. The most serious items were then reopened by hand.

| | Run A, a new feature | Run B, changes across an existing site |
|---|---|---|
| Session length | about 64 hours | about 20 hours |
| Context compactions | 13 | 4 |
| Agents launched | 167 | 69 |
| Pull requests merged | 34 | 4 |
| Lines added | about 115,000 | about 90,000 |
| of which tests | about 61,600 (53%) | about 30,400 (34%) |
| of which source | about 47,800 (41%) | about 34,500 (38%) |
| of which generated files | about 100 (under 1%) | about 23,400 (26%) |
| Lines deleted | about 7,300 | about 14,100 |
| Files created | 207 | 535 |
| Existing files changed, moved or deleted | 162 | 849 |

The line and file rows cover the 34 and the 4 pull requests. Each is counted from the pull
request's diff at its merge, with renames detected. A line that one pull request added and a
later one rewrote counts twice, so the rows measure work done, not the size of the result. The
rest of the added lines are documentation.

The two runs were different work. Run A was new code: more files created than changed, about 16
lines added for each one deleted, over half of the additions tests. Run B was edits across an
existing site: 849 existing files changed against 535 created, and a quarter of the additions
generated files.

| Class of incident | Run A | Run B |
|---|---|---|
| Shared-resource collisions, on things a worktree does not separate | 22 | 14 |
| Context loss | 9 | 11, four of them within two hours of a compaction |
| Rulings by the orchestrator later found wrong | 11, and 2 plans | 7 |
| Defects merged and found later | 17 | 2 from the epic itself |
| Findings caught before merge | about 368 | about 145 |
| Agent misbehaviour (a false report, a skipped step, work outside the brief) | 11 | 19 |
| Rulings taken by the orchestrator and not the user | about 96 of 107 | 138 of 142 |

What the counts say:

- Rules the kit had already written down were broken on the long run. The program note was to
  take its times from the machine: its clock ran up to 15 hours ahead and went backwards three
  times. The log was to be rotated at about 300 lines: it reached 4,913. Sessions were to agree
  in writing: the message between them was refused, and they overwrote each other's code on a
  shared backend eight or more times.
- Scripts and checks held: a lock directory, a check that deployed code is a subset of the
  tree, a save, change, restore and read-back routine for an account-wide setting, a kill switch
  that kept unfinished work out of production, a skew check before each production deploy.
- The worst escaped defect passed more than 70 review and verification runs, because every agent
  worked from the same acceptance criteria. A review of the merged code found it after about 37
  hours. The kill switch kept it from production.

Limits of these counts: one agent classified each incident, from the session's notes in one case
and from the transcript in the other, so the two columns are not measured the same way. "About"
marks a lower bound summed from review reports. The 34 pull requests of run A are the ones that
carry the epic in their title. The session's own note counts 41, and 5 more in a second
repository, which the rows above leave out. Both projects are private and are not named.

The kit's response: `shared-resources.md` with `lock.py` and `claims.py`,
`note.py`, `tick.py`, the failure-mode pass, the rules on who decides, and the `retro` skill.

## How the way of working changed

Read from the prompt history, with the month each practice first appears.

| When | What appears |
|---|---|
| April | One session at a time. "How should this be done?" before each change, design grilling, smoke tests. I committed everything myself |
| May | Design documents and plans as the output of a grilling. Staged prompts pasted into fresh sessions. The first worktree, for parallel work. The first subagent, the first "do not stop until everything is done" |
| June | The first overnight mandate. Runbooks. Agents with a clean context as checkers |
| July | GitHub issues and pull requests become the unit of work. A model per role. Rented GPU fleets watched by a loop. The rule that Claude never commits without my word |
| Late July | The main session becomes an orchestrator that does not code. Verifier agents. Merge grants scoped to one piece of work. A ledger for a program that runs for days |
| September | Epics with sub-issues, worked in waves over more than a day |
| October | Agent definitions for implementer and reviewer. Merge queues and chain scripts |
| November | Goals that run for a week, with watchers, wake-ups and a note that survives every restart |

The kit is the state at the end of that table. Where a skill encodes a rule, the rule came from a
specific correction, and where a reference file lists a trap, the trap happened.
