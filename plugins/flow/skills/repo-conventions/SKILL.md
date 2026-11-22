---
name: repo-conventions
description: Set up or audit a repository's agent instruction file (AGENTS.md, with CLAUDE.md pointing at it) so it carries the house workflow, issue before code, branch and PR rules, gates with zero warnings, smoke test, adversarial review, and docs that move with the code. Use when starting a new repository, when the user says "update the claude md", "instruct it to always ...", "add instructions for ...", "audit the CLAUDE.md, it grew too much", or asks for the same conventions as their other projects.
---

# Repository conventions

## The file

- `AGENTS.md` is the source. `CLAUDE.md` contains the single line `@AGENTS.md`, so other agents
  read the same rules.
- It is an index: what the repository is, the commands, the rules. A change adds about ten lines
  at most, the rule plus a link. The story behind a rule, measurements and incident accounts go in
  `docs/architecture.md`.
- Rules for one part of the code go in `docs/agents/<part>.md`, with one line in the index:
  "read this before touching <part>".
- An instruction file that keeps absorbing history ends up larger than a context window. One grew
  to 615 KB. When the file passes a few hundred lines, split it, and add a test that fails when it
  grows past the budget.

## A new repository

1. Look at the owner's other repositories first and copy their choices. Do not invent a stack or
   a layout when a reference project exists. Say what you reused and from where. When a sibling
   repository already solved the same problem, port its exact shape, cite the commit, and add a
   test that fails if the fix is undone.
2. Start from [references/AGENTS.template.md](references/AGENTS.template.md) and fill the
   placeholders. Stack choices and gate commands are in
   [references/stack-defaults.md](references/stack-defaults.md).
3. Ask the user only for what differs between their repositories (next section).
4. Add the pieces the file promises: a CI workflow that runs the gates, release tooling, an
   `.env.example`, a `docs/runbook.md` and a `docs/decisions.md`.

## Choices to write down, because they differ per repository

- the integration branch, and whether a separate production branch exists
- squash merge or merge commits
- who closes issues, and whether closing keywords are allowed next to an issue number. Where an
  integration branch feeds a release PR, closing keywords have closed issues in bulk at release
  time, so those repositories forbid them and close by hand
- whether the agent may commit, push and merge without asking
- the language of the interface text, and the language the assistant answers in
- where secrets live
- how browser checks run on this machine, and where screenshots are stored
- full end-to-end suite locally, or targeted specs with the full run left to CI

## When the user states a rule

"Instruct it to always run lint and format after each change" means edit the instruction file.
Edit it where the user is working when they asked for it there. Otherwise edit it on a branch,
and say in either case whether the change is committed (`save-state`).

- Put the rule in the section it belongs to, in one or two lines, with the reason when the reason
  is not obvious.
- A rule about one conversation or one epic goes to memory instead (`save-state`).
- A rule that should hold in every repository belongs in the user's global instructions. Say so
  and ask before editing those.

## Auditing an existing file

- every command in it exists and runs
- the gates listed match what CI runs
- no section tells the story of a change that the docs should hold
- no two rules contradict each other, and none contradicts the user's global instructions
- generated blocks from tools (framework notices, plugin routing tables) are marked as such and
  kept apart from the house rules
- report what you would move out and where, then move it once the user agrees
