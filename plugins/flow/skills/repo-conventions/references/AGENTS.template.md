# Working in this repository

This file is the agent index: what the repository is, the commands, the rules. Mechanics,
measurements and incident stories go in `docs/architecture.md`. A change adds at most about ten
lines here, the rule plus a link. `CLAUDE.md` contains only `@AGENTS.md`.

## Project

<One paragraph: what it is, who uses it, the stack.> Package manager: <bun | uv | go | cargo>.
GitHub: `<org>/<repo>`.

Language: English for code, identifiers, comments, test titles, docs and every GitHub artifact.
Text the user reads is in <UI language>. The assistant answers in <conversation language>.

## Commands

```sh
<install>                # for example: bun install, uv sync --locked
<dev>                    # port <port>; check the port is free first, never kill another server
<check>                  # every gate below in one command
<test>
<build>
<smoke> <base-url>       # read-only probes against a running or deployed instance
```

## Workflow

1. Issue before code (`gh issue create`). Body: Problem (the observed behaviour, without the
   fix), Acceptance criteria (checkable by someone else), Out of scope. A change too small for an
   issue joins an existing one.
2. Branch from `<integration-branch>` as `feat|fix|chore|docs/<issue#>-slug`. Never commit to
   `<production-branch>` or `<integration-branch>` directly. Parallel agents each take their own
   `git worktree`, copy the local env file in, and never run the repo-wide formatter from there.
   For UI work take the before screenshots now, on the clean branch.
3. Implement in small commits, then pass every gate. A red gate is never ready for review.
4. Smoke test. Never ship a change you have only read. Run the app, walk the acceptance criteria
   on what you changed, then one adjacent flow. In a browser: clean console, no failed requests,
   light and dark, about 390 px and about 1440 px, the keyboard path. Record the commands and
   their real output. A check you did not run is reported as skipped.
5. Adversarial review. A separate agent with fresh context gets the diff and the acceptance
   criteria, assumes the change is broken, and names what the smoke test missed. Each finding is
   fixed or rejected in writing after you confirm it in the code. Rerun the gates after fixes.
6. PR to `<integration-branch>`. Title: a Conventional Commit with the issue number in
   parentheses. Body: what changed and why, how it was verified (commands, output, review findings
   and how each was settled), before and after screenshots for visual changes, known gaps.

<Commit, push and PR policy: "only after the owner says so in this conversation" | "the agent
commits, pushes and opens the PR; merging waits for the owner" | "the agent may merge to
<integration-branch> once verified and smoke tested">

Hygiene: one issue, one branch, one PR, one concern; under about 400 changed lines; a draft PR
early for larger work. Reproduce a bug before fixing it. Every bug fix gets a test that fails
before and passes after. Treat unexpected changes in the working tree as the owner's work.

## Commits and releases

`type(scope): summary (#issue)`. Release tooling builds the version and the changelog from these,
so choose the type by what the change means to a user. A visible fix filed as `chore` never
reaches the changelog. PRs merge by <squash, the title becomes the commit | merge commit, one
commit per concern>.

<Issue closing: "`Closes #N` in the PR body" | "no closing keyword next to `#N` anywhere; the
agent closes the issue by hand after the merge, with a comment that maps each criterion to the
PR">

Never hand-edit the changelog, the release manifest or the version field.

## Gates

After every code change and before saying a task is done, all of these pass with zero errors and
zero warnings:

- format: <command>
- lint: <command>
- types: <command>
- test: <command>
- build: <command>

Run what CI runs before pushing. Fix the code, not the rule. A suppression covers one line and
states its reason. Never weaken, delete or skip a test to get green.

New behaviour ships with tests in the same change. A pure function gets a happy path and an edge
case, a CLI flag gets a test of the branch it switches, a regex gets a positive, a negative and
each quirk. Tests never touch the network or a live service.

## Code

- <Language rules. TypeScript: strict, never `any`, never `!`, unions for known strings,
  interfaces for object shapes, `as` only at boundaries.>
- Environment variables are read through one validated schema (`<path>`), never raw. A new
  variable also goes in `.env.example`, the README table and the runbook.
- A schema change ships with its migration in the same PR.

## UI

Read `PRODUCT.md` and `DESIGN.md` before any UI work. Reuse the components in
`<components dir>` first, then the component registry, and build from scratch only when neither
has it. Semantic tokens only, never hard-coded colours. Every token is defined for light and
dark. External links open in a new tab.

## CLI

- Long-running commands print a one-line startup summary at once, then a progress bar on stderr
  (done over total, ETA, live outcome counters), plain periodic lines when stderr is not a
  terminal, and the resume command after Ctrl-C.
- Commands that write are dry-run by default and need `--apply`.
- Exit codes: 0 done, 1 failed, 2 not configured, 130 interrupted.

## Secrets

Secrets live in <secret store> and in a gitignored local env file. `.env.example` holds names
only. Never print, log, commit or paste a secret, and never ask the owner to paste one into the
chat.

## Docs move with the code

- `docs/runbook.md`: a new or changed command, flag, default, env var, schedule or recovery step
  updates it in the same PR.
- `docs/decisions.md`: each settled design decision, dated, in the PR that makes it.
- `README.md` and `docs/architecture.md` for every meaningful change: a new flag, behaviour,
  default, module, route, dependency, env var or failure mode.

## Cleanup

When a run ends, stop the servers you started, remove the worktrees you cut after their PR
merged, and say in the recap what was cleared.
