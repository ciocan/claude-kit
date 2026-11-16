---
name: overnight-handoff
description: Prepare an unattended run before the user leaves and report on it when they return. Clear their blockers first, write down what they authorised, queue enough work, and leave a morning recap. Use when the user says "I'm going to sleep", "I'll go to bed", "you have the reins", "work autonomously", "anything needed from me before I go?" or "continue until it's done", and when they ask in the morning what happened overnight.
---

# Overnight handoff

## Before they go

1. List everything that will stop you while they are away: decisions, secrets, logins, commands
   the permission classifier refuses, migrations they apply themselves. Number the list, one
   action per item, each with its exact command (`owner-scripts`). Ask now. A blocker found at
   02:00 costs the night.
2. Repeat the grant back with its edges: what you may merge, deploy and run, the spending limit,
   and what to do near a usage limit.
3. Queue enough ranked work to last until morning. Put items that end at a step only they can do
   last. Hold PRs that carry a migration they must apply.
4. Write the mandate note before starting. Template below.

## While they are away

Covered by a night grant:

- the queue they saw before leaving
- rerunning a step that stopped
- merging under the standing review rule
- closing issues on evidence

Not covered, whatever the wording of the grant:

- anything new and destructive: dropping data, bulk resets, index-wide deletes
- applies outside the queue they saw
- spending beyond the stated limit
- anything that reaches people outside the team

Those wait for the morning with their exact command.

Rules for the night:

- A permission refusal is final. Record the line, move to the next item. Do not retry it in
  another form.
- Decide ordinary questions by your own recommendation and write each decision on the issue or
  the PR, so the trail exists outside this session.
- Smoke after every deploy. Keep the main branch and the deployed product working at every step.
  Never stop for the night in the middle of a chain.
- Log each production run with its time.
- Check usage between waves. Near the limit, stop launching, let agents finish, and schedule a
  wake-up for the reset (`orchestrate`, models and limits).
- Update the state note at each merge and launch (`save-state`).

## Mandate note

```markdown
---
name: overnight-authorisation-<date>
description: "User <date HH:MM UTC>: '<their words>'. What it covers for this night"
metadata:
  type: feedback
---

On <date> at <time UTC> the user wrote: "<exact words>". Running at that moment: <jobs, agents>.

Covers: <the queue put to them, as a list>.
Not covered: <new destructive steps, applies outside the queue, spend above <limit>>.
Refused commands wait for the morning with their exact line. Each run is logged in <path>.
Ends: when they are back.

**Why:** <what would stall without it>.
**How to apply:** <order of the queue>. State in [[<state note>]]. Leave a morning recap.
```

## Morning recap

Lead with the headline, then keep this order:

1. Long runs: what completed and when, the figures, the failures with their cause.
2. Merged, with issue numbers. Held, with what each waits for.
3. Steps that failed, the cause, and the recovery command.
4. Commands refused to you, as a paste list in the order they must run.
5. Decisions you took on their behalf, each with how to overrule it.
6. What they owe: decisions, secrets, click-throughs, housekeeping.
7. What you cleaned up, and the usage or money spent.

Save the recap as a memory note too (`morning-recap-<date>`), so a new session can present it.
