# Getting started with flow

A walkthrough for someone who has never used this kit. It takes you from install to a merged pull
request, then covers the habits that keep the workflow cheap to run. The README lists every
skill. This page is about the order to use them in.

## The idea in one minute

You talk to one Claude Code session. That session does not write the code. It plans, sends agents
to build and check the work, and handles git and GitHub. Every unit of work goes through the same
loop:

```mermaid
flowchart LR
    A[Issue] --> B[Worktree] --> C[Implementer] --> D[Reviewer]
    D -- findings --> C
    D --> E[Smoke test] --> F[Pull request] --> G[Merge] --> H[Issue closed]
```

Three things follow from that design.

- You steer with short sentences: "deploy an agent to fix this", "how is it so far?", "merge it".
  The sentences load the skills. You never have to name one.
- "Done" means a second agent reviewed the change and something ran the real app. Passing tests
  alone do not count.
- Nothing is committed, pushed or merged until you say it may be.

## Before you start

- A recent Claude Code, signed in, with both plugins installed (see the README).
- The GitHub CLI, signed in. Check with `gh auth status`. The skills assume GitHub.
- A git repository with a GitHub remote.
- An instruction file, `AGENTS.md` or `CLAUDE.md`, that names your gate commands: lint, types,
  tests, build. Agents read it before they touch anything. Step 2 below writes one.
- Optional: the `code-review` and `mattpocock-skills` plugins. `bootstrap/install.sh` adds them.

## Your first session

### 1. Check the setup

Open Claude Code in your repository and run:

```
/flow:start
```

It checks the list above, tells you what is missing with the fix for each item, and proposes a
small first task.

### 2. Give the repository its rules

```
set up AGENTS.md for this repository with the house conventions
```

Claude reads the repository and asks only what it cannot see: the branch you integrate on, squash
or merge commits, who closes issues, whether agents may commit. This file matters more than any
prompt you will type later, because every agent starts by reading it.

### 3. Run one small task through the loop

Pick something that would be a ten-line pull request. A real bug is better than a made-up one.

```
deploy an agent to fix <the bug>. file the issue first.
when it is verified and smoke tested, file the pr.
you have permission to commit and push for this.
```

What happens, in order:

1. Claude files the issue with acceptance criteria.
2. It cuts a worktree and a branch, so your own checkout is never touched.
3. An implementer agent builds the fix and runs the gates.
4. A reviewer agent that did not write the change looks for bugs. Findings go back to the
   implementer, three rounds at most.
5. A verifier runs the real thing and records what it saw.
6. Claude commits, pushes and opens the pull request with the evidence in the body.

While it runs, ask whenever you like:

```
how is it so far?
```

You get about fifteen lines in a fixed order: progress and ETA, what is in flight, what landed,
what is blocked, and a numbered list of what it needs from you.

### 4. Land it and tidy up

```
merge it and close the issue
cleanup
```

The merge waits for CI. The cleanup removes the worktree and branch only after GitHub reports the
pull request as merged.

## A larger piece of work

Design first, then let agents build it in parallel.

```
/grilling <the feature, with the constraints you already know>
```

That command comes from the `mattpocock-skills` plugin. Without it, write "ask me the design
questions for <feature>, numbered, with your recommendation for each". Either way you answer in a
few words:

```
q2 b, q5 keep the old endpoint, agree with the rest
```

Then:

```
file the epic with detailed sub-issues
deploy agents to work on the epic. you manage everything from here.
you may commit, file prs and merge to dev once each one is verified and smoke tested.
```

Claude works the sub-issues in waves of up to three agents and posts progress on the epic. If
your version of Claude Code has `/goal`, set one with an end state someone can check, for example
`/goal complete epic 42, everything verified in the browser`.

## Running for days or weeks

Some goals outlast a session: a backfill with its fixes, a move from one data store to another, a
backlog worked until it is empty. The loop stays the same. What changes is that the session is
compacted, restarted and rate-limited along the way, and you are away for most of it.

### Set up once

1. **A goal that can be checked.** Name the checks, because the goal is judged only from what
   appears in the conversation:

   ```
   /goal epic 42 is closed: every sub-issue merged, the gates green on main, the smoke passing
   on production. Do not stop until it is all done and verified.
   ```

2. **A grant for the stretch.** "You have permission to commit, file prs and merge to dev for
   this goal." Say what stays yours, usually production writes and anything that deletes.
3. **A machine that stays on.** The session lives in a terminal on it. Run it under tmux or as a
   background session on a server, and use Remote Control (`/rc`) to look in from a phone.
4. **Auto mode.** A goal does not change the permission mode, and unattended turns need it. What
   auto mode refuses comes back to you as commands to paste.

### What Claude keeps

- One program note per goal: the goal in your words, the definition of done, your grants, the
  holds, and a dated log. It is what every restarted session reads first.
- A paste file with the commands only you can run, numbered, in order.
- Long jobs started detached, each ending in a marker line, each with a watcher or a scheduled
  check. Four scripts ship for this: detached runs, follow-ups, chains of steps, and a merge
  train that merges PRs in order and stops at the first doubt.

### Your part

| When | You type | You get |
|---|---|---|
| Morning | "how is the goal progress?" | What landed overnight, what failed and why, the pastes you owe in order, decisions by size |
| Any time | "how long until the goal is complete?", "what slows it down?" | An ETA from the measured rate, and the bottleneck with a number |
| Any time | "what else can run in parallel?" | Free slots filled from the queue |
| Evening | "I'm going to sleep, anything needed from me?" | Every blocker now, then one plan for the night |
| After a limit | "continue, the limits are reset" | Agents resumed with their context |
| Before `/compact` | "can I compact this session?" | Yes or no, after the state is written down |
| After a restart | "continue" | The session re-anchors from the note, restarts its watchers, and goes on |

### What to expect

The kit's rules for long runs come from nine goals that ran between half a day and nine days. Code
was rarely what stopped them. The common stalls were a command only the owner could run, sitting
for six to ten hours, a usage limit that killed every agent, and a session that went idle
because the watcher it relied on had died. So the three things that keep a long run moving are
yours: answer the evening question, run a paste when the push arrives, keep the machine on.

Some limits no skill removes:

- A reboot ends the session and every job with it. Afterwards run `claude --resume` and type
  "continue".
- While background work runs, a goal checks in a few times and then waits for you. If you find
  the session idle with work pending, type "continue".
- Scheduled tasks inside a session expire after seven days.
- Work that must run with the machine off belongs in a cloud scheduled task, which starts from a
  fresh clone and sees none of your local state.

The mechanics are in
[keeping going](../plugins/flow/skills/long-haul/references/keeping-going.md), the note
template in [program note](../plugins/flow/skills/long-haul/references/program-note.md), and the
full list of stalls with their cost in
[stalls](../plugins/flow/skills/long-haul/references/stalls.md).

## The phrases

| You say | What you get |
|---|---|
| "deploy an agent to fix X" | the whole loop for one issue |
| "you manage everything from here" | Claude orchestrates and stops asking about routine steps |
| "work here, no branch" | a direct edit in your checkout, no agents |
| "how is it so far?" / "whats next?" | a status report, or a ranked list of next actions |
| "what do you need from me?" | only the steps that are yours, with exact commands |
| "make sure it's smoke tested" / "how was it verified?" | the real app is run, and you see the commands and output |
| "file the pr" / "merge it" / "close the issue" | the shipping steps, with guards |
| "investigate without bias" | a fresh agent that has not seen the first diagnosis |
| "why is this number so high?" | the value traced to the layer that produced it, fixed there, existing rows repaired |
| "check the failed ones and see what can be done" | failures by cause, and the command that reruns only those |
| "do another round" | one more sample, check and fix pass toward a stated accuracy target |
| "can I compact this session?" | state is written to notes, then a yes or no |
| "I'm going to sleep, anything needed from me?" | blockers cleared now, a queue for the night, a recap in the morning |
| "cleanup" | servers stopped, merged worktrees removed, disk reported |
| "/goal ...", "do not stop until it is done and verified" | a run that lasts days: a program note, watchers, a recap each morning |

If a sentence does not load the skill you expected, name it: `/flow:orchestrate`,
`/flow:status-report`, and so on.

## Habits that keep it cheap

1. **Match the tool to the job.** One unit of work runs at least three agents: implementer,
   reviewer, verifier. That is several times the tokens of a direct edit. Use the loop for
   anything worth a pull request. For a one-line change say "work here".
2. **Start with one agent.** Three at once is the default cap, and all of them draw on the same
   usage limit as your main session. Go parallel once the first loop has run clean in your
   repository. Say "stay within the session limit" when a wave is large.
3. **Grant narrowly, once.** "You have permission to commit, file prs and merge for this epic"
   removes dozens of questions. A grant covers one repository and one goal. It does not carry to
   the next conversation.
4. **Answer by number.** Claude numbers every choice. "Do 1 and 3" and "agree with the rest" are
   complete answers.
5. **Ask for evidence.** "How was it verified?" should come back with commands and their output,
   plus a plain statement of what could not be checked.
6. **Keep the main session out of the code.** Its context is the scarce resource. If it starts
   reading files to answer a question, say "you're the orchestrator, deploy an agent".
7. **Save before you compact.** Ask "can I compact this session?" first. Agents in flight can
   only be resumed if their ids and worktrees were written down.
8. **Hand over before you leave.** One question at bedtime finds the blocker that would otherwise
   stop the night at 02:00.
9. **Close the day with "cleanup".** Worktrees, containers and dev servers pile up fast when
   three agents work in parallel.

## Making it yours

- **Models.** The three agents run on Opus: the implementer and verifier at high effort, the
  reviewer at xhigh. Override per task in plain words ("use sonnet for the implementers"), or
  fork the repository and edit the `model` and `effort` lines in `plugins/flow/agents/`.
- **Repository rules win.** Merge style, branch names, who closes issues and whether agents may
  commit belong in your `AGENTS.md`. The skills defer to it.
- **Slots.** "Run at most two agents" or "you can run five" changes the cap for the session.
- **Standing rules.** "From now on ..." is written to Claude's memory for that project. Rules for
  every project go in `~/.claude/CLAUDE.md`. `bootstrap/CLAUDE.global.md` is a starting point.

## When it does not do what you expect

| What you see | What to do |
|---|---|
| Claude edits code itself instead of sending an agent | Say "you're the orchestrator, deploy an agent" |
| An agent finishes but nothing is committed | Give the grant: "you have permission to commit and push" |
| A command is refused by the permission system | Ask "what do I need to run?" and paste the line it gives you |
| Agents died at a usage limit | After the reset say "continue, the limits are reset". They resume with their context |
| The review keeps finding things | After three rounds Claude closes the gaps itself or files follow-up issues. Ask for the list |
| "Smoke tested" with no proof | Ask "how was it verified?". No commands and output means it was not |
| The skill list looks stale after an update | `/reload-plugins` |

## Reading further

- [Brief templates](../plugins/flow/skills/orchestrate/references/briefs.md) for the four agent
  roles, if you want to see what the agents are told
- [Traps](../plugins/flow/skills/orchestrate/references/traps.md) and
  [git traps](../plugins/flow/skills/ship-pr/references/git-traps.md), each with the incident
  behind it
- [Models and usage limits](../plugins/flow/skills/orchestrate/references/models-and-limits.md)
- [A starter AGENTS.md](../plugins/flow/skills/repo-conventions/references/AGENTS.template.md)
