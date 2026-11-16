# Models and usage limits

## Default roles

| Role | Model | Effort |
|---|---|---|
| Orchestrator, and the closing review on risky changes | the strongest model available | the session's |
| Implementer | one tier below | high |
| Reviewer | one tier below | xhigh |
| Adversarial verifier, final smoke | one tier below, or the strongest for the last gate before a release | high |
| Researcher on a judgement question | one tier below | default |
| Inventory and search (list files, collect facts) | a small fast model | default |

With Claude models at the time of writing that reads: Fable orchestrates, Opus builds and reviews,
Sonnet or Haiku collect. Edit the table to match the plan you are on.

The split exists because the two budgets are separate. The orchestrator's window stays free for
planning and judgement while the workers spend the other model's window.

## Rules

- Set the model and the effort on every launch. Leaving effort blank gives a different agent each
  time.
- A model the user names for a task wins over the table.
- "From now on" and "until I say otherwise" are standing rules. Write them to memory with the date
  and the user's words.
- Do not use the small model to implement or review unless the user asks for it.
- Complex slices may go to the strongest model at low or medium effort. Say that you did.
- When the user asks "which model are the workers on?", answer from the launches you made.

## Staying inside the limits

1. Check before each wave:

   ```sh
   npx -y ccusage@latest blocks --active --json
   ```

   It gives the start of the active five-hour block, the spend so far and the time remaining.
2. At 90 percent of the five-hour or the weekly window, launch nothing new. Let the agents in
   flight finish, merge what is green, and post the state on each open PR.
3. Schedule a wake-up for when the window resets. On waking, check the block's start time. A new
   start time is the proof that the window turned over, elapsed time alone is not.
4. After the reset, resume stopped agents with SendMessage.
5. Other sessions draw on the same limits. When the user says other workspaces are running, plan
   for a share of the window.

When the user says the limit is not a concern ("I can reset it with another subscription"), stop
deferring work for budget and mention usage only near a hard stop.

## A wave

Three implementers, plus one or two reviewers for slices already in review. More than that has
ended with every agent dead at the limit, or with the host out of memory.
