---
name: issue-sweep
description: Sweep a repository's open issues and pull requests. Close what merged work already did, flag stale and duplicate issues, list what can merge now, and rank what is ready to work. Use when the user asks "are there any orphan issues?", "close all completed issues", "triage the open issues", "check open PRs and see what can be merged" or "what can run in parallel?", and before picking the next item for an agent.
---

# Issue sweep

Open issues are not a reliable backlog. A PR without a closing reference leaves its issue open,
and an agent briefed on that issue burns its budget finding the work already on the main branch.

## Orphans: done but still open

For each open issue:

1. Search for the work: `gh pr list --state merged --search "<number or key words>"` and
   `git log --oneline --grep "<key words>" origin/<main>`.
2. Read the acceptance criteria against the code paths the issue names. A merged PR with a
   matching title is a lead, not proof.
3. When it is done, close it with a comment that names the PR.

Closing keywords (`Closes #12`) only fire when the PR merges into the default branch. A repository
that integrates on `dev` and releases to `main` needs its issues closed by hand at merge time, or
a small workflow that does it.

## Stale, duplicate, superseded

List them with the reason and the issue or PR that replaces each. Close the ones with a clear
replacement and point to it. Ask before closing anything you judged stale without merged work
behind it.

## Pull requests

- mergeable now: checks green, reviewed, not a draft
- needs a rebase or has conflicts
- red: say for each whether the failure looks like a flake or a real defect
- release PRs opened by release tooling are the owner's to merge. Leave them.

## What is ready

- Issues whose blockers have merged get unblocked and relabelled.
- Rank the ready ones: a production failure or a data defect the user flagged, then the current
  epic's next slice, then follow-ups. Use the repository's priority label when it has one.
- Mark which ready items touch separate parts of the code and can run in parallel.

## Reports from outside

A bug report from a user or a partner gets a verdict first: valid, not a bug, or cannot
reproduce, with the evidence. Answer in the reporter's language. When the user asks for it,
comment how the bug should be fixed without writing the fix.

## Output

A numbered list per section, so the user can answer "close 1 to 4, merge 6, start 7 and 9". When
you run as an orchestrator with free agent slots, start the top ready items and say which and why.
