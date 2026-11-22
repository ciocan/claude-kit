---
name: status-report
description: Answer a progress question with a short report in a fixed order, percent done and ETA, what is in flight, what landed, what is blocked, and a numbered list of what the user must do. Use when the user asks "what is the status?", "how is it so far?", "how long until done?", "is all done?", "how is the goal progress?", "whats next?", "what do you recommend?", "what do you need from me?" or "what decisions do I need to take?".
---

# Status report

The user asks these questions many times a day, often from a phone between other things. Answer in
under 15 lines, in the same order every time, from measurements taken now.

## Measure first

A status written from memory is a guess. Before answering, look at what can have moved since the
last report:

- running jobs: their counters, the tail of their logs, whether the process is still alive
- agents in flight: which are running, which handed back, which died
- pull requests and CI: `gh pr list`, `gh pr checks <n>`, `gh run list --limit 5`
- the queue: what is ready, what is blocked
- deployed state: what is live where. Measure it again before repeating an earlier claim, and
  give the time of the measurement. "Not live yet" was once repeated for hours after it had
  stopped being true

## Order of the report

1. One line with done over total or a percent, and an ETA. Say what the ETA rests on, for example
   the rate over the last 20 minutes. If no honest ETA exists, name the unknown.
2. In flight. One line per agent or job: what it does, which issue, which model, how far along.
3. Landed since the last report. PR numbers merged, issues closed, jobs finished.
4. Blocked or slow. What and why. For "what slows it down?" name the bottleneck with a number.
5. Needs from you. A numbered list where each item is one action with the exact command or link.
   Write "Nothing needed from you" when that is true.

## Variants

- "Whats next?" and "what do you recommend?" get a ranked, numbered list of next actions. The
  first item is the recommendation, with one line of reasoning. The user answers "go", "agree" or
  "do 1 and 2".
- "What do you need from me?" gets part 5 only, complete. At bedtime, follow `overnight-handoff`.
- "Is it done?" gets yes or no first, then what is left.
- "Can I compact?" is a different question. Follow `save-state`.
- "How is the goal progress?" on a long run is answered from the program note's top block and
  the checks in its definition of done (`long-haul`).

## Rules

- Number everything the user may choose from, so they can answer by number.
- Give times in one zone and name it. Take the time from the machine, never from memory.
- Durations come from the tracker's merge and close times (`gh pr view <n> --json mergedAt`,
  `gh issue view <n> --json closedAt`), not from the note. A note's clock can drift by hours.
- Leave out what has not changed, and do not restate the plan.
- Report failures as plainly as successes: a red check, a failed run, an agent killed by a usage
  limit, a job that stalled.
- When you already acted on your own recommendation, say what you did and what the user can
  overrule. Ask only about decisions that are theirs: money, product promises, architecture,
  anything that drops data or cannot be undone, anything that reaches people outside the team.
