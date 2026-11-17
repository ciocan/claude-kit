---
name: orchestrate
description: Run the main session as an orchestrator that sends implementer and verifier subagents through the loop from issue to merged PR (worktree, build, review, smoke test, PR, merge, close) and keeps agent slots full. Use when the user says "deploy an agent", "deploy agents", "same machinery", "you're the orchestrator", "you manage everything from here", "work with subagents", or asks to work an epic, a wave or a list of issues.
---

# Orchestrate

"The machinery" is one loop, the same for every unit of work: issue, worktree, implementer, fresh
reviewer, smoke test, PR, merge, close. The main session runs the loop and stays out of the code.

## Roles

- The orchestrator plans, slices, writes briefs, rules on open questions, triages review findings,
  commits and pushes, opens and merges PRs, deploys what it may, closes issues and keeps the state
  note.
- The orchestrator does not read code to answer a question itself. Reading a file to write a brief
  is fine. Its context is the scarce resource, and every inspection loop spent inline is gone.
- Implementers build and test in their own worktree. Reviewers and verifiers read and run, and
  leave the tree as they found it.
- The user's word wins. "Work here" or "do it directly, no subagent" means do it inline.

## One unit of work

1. Check the work is still needed: `gh pr list --state merged --search "<n or key words>"` and
   `git log --grep`. Open issues are not a reliable backlog.
2. Check the checkout is current: `git fetch origin && git rev-list --count HEAD..origin/<main>`.
   Never pull or edit the user's own checkout. Cut a worktree.
3. Make sure an issue exists with acceptance criteria. File it when it does not.
4. Cut a worktree and a branch from the integration branch with `git -C <repo> worktree add`. One
   worktree per issue, set up on its own (its own virtualenv, its own install).
5. Brief an implementer. The templates are in [references/briefs.md](references/briefs.md).
6. Send a reviewer that did not write the change. Its findings go back to the same implementer
   with SendMessage, which keeps that agent's context. Three fix rounds at most. After that, close
   the last gaps yourself or file them as follow-up issues.
7. Smoke test the real thing. See `smoke-test`.
8. Rerun the cheap gates yourself after the agent's last edit, then land the change with
   `ship-pr`.
9. Close the issue with the evidence. Run what the merge owes: migration, rebuild, redeploy.
   Remove the worktree only after the PR reads `MERGED`.

Changes to money, auth, migrations or anything that deletes get one more review on the strongest
model before the merge.

## Slots

- Three agents at once unless the user set another number.
- When a slot frees, start the highest-impact item that is unblocked, and say which one and why.
  Rank a production failure or a data defect the user flagged first, then the epic's next slice,
  then follow-ups.
- Look for the independent part of a chained slice and run it in a second worktree. Serial work is
  the fallback, never the default.
- Slices that edit the same file land one at a time.
- Items that wait on the user (a decision, a secret, a paste) wait. Name the action they owe.
- A long production job holds back the merges that would restart it. It never holds back
  development.

## Models and limits

Name the model and the effort on every launch. The defaults and the usage rules are in
[references/models-and-limits.md](references/models-and-limits.md). A model the user names wins.
"Until I say otherwise" lasts across sessions, so write it to memory.

## What every brief carries

The agent has none of your context. Each brief names the worktree, a scratch directory of its own,
what to read first, the gates as exact commands, who commits, when to stop and report, and the
shape of the report. Ask for the report as the agent's final message.

## State and reporting

After every merge, launch and hand-back, update the state note (`save-state`). Each recap says what
merged, what is in flight, what you started and why, and what waits for the user
(`status-report`). When the work will outlast the session, follow `long-haul` as well.

## Before the first launch

Read [references/traps.md](references/traps.md) once per session. Every line in it cost a lost
branch, a dead shell or a full disk.
