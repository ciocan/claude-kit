# claude-kit

How I run Claude Code, packaged so it works on another machine or for another person. Two
plugins and a bootstrap script.

## What it is based on

Seven and a half months of daily work with Claude Code on two machines, from 3 April to
17 November 2026. Measured, not estimated:

| | |
|---|---|
| Pull requests merged | 2,188, in 39 repositories (31 private, 8 public) |
| Commits co-authored by Claude | 8,444 |
| Issues closed | 1,805 |
| Prompts I typed | 12,418, in 1,010 sessions, on 185 days |
| Agents launched | 2,621 in the transcripts still on disk, which reach back to 22 September |
| Corrections Claude wrote down | 89 notes, among 462 memory notes |

Of those prompts, 379 sent an agent to do the work, 331 asked for a smoke test, 114 opened a
design grilling, 59 set a goal to run unattended, and 35 handed over for the night.

Each skill answers a request I typed dozens of times. Each trap in the reference files cost a
lost branch, a dead shell or a full disk at least once. What every number counts, and what it
cannot tell apart, is in [docs/evidence.md](docs/evidence.md), next to what went wrong: two long
runs taken apart afterwards had 22 and 14 collisions on things a worktree does not separate, and
17 defects that were merged before anyone found them.

## Install

In Claude Code:

```
/plugin marketplace add ciocan/claude-kit
/plugin install flow@claude-kit
/plugin install unslop@claude-kit
```

Or from a checkout, with the third-party pieces the skills lean on:

```sh
git clone https://github.com/ciocan/claude-kit.git && cd claude-kit
bootstrap/install.sh                      # dry run, prints the plan
bootstrap/install.sh --apply              # minimal profile
bootstrap/install.sh --profile full --apply
```

## Updating

```sh
claude plugin marketplace update claude-kit   # fetch the latest catalog from GitHub
claude plugin update flow@claude-kit
claude plugin update unslop@claude-kit
```

Then run `/reload-plugins` in any open session, or restart Claude Code.

- Run the marketplace update first. The plugin update reads your local copy of the catalog, and
  without a refresh it reports nothing new.
- `claude plugin list` shows the version you have installed.
- From inside a session, put `!` in front of a command to run it without leaving.
- Each [release](https://github.com/ciocan/claude-kit/releases) carries the version the plugins
  report, and `CHANGELOG.md` says what changed in it.

## New here?

After installing, open Claude Code in one of your repositories and run `/flow:start`. It checks
your setup and proposes a small first task. [The guide](docs/guide.md) walks through a first
session, the phrases to use, and the habits that keep the workflow cheap.

## The `flow` plugin

One loop, the same for every unit of work: issue, worktree, implementer, fresh reviewer, smoke
test, PR, merge, close. The main session orchestrates and stays out of the code.

| Skill | Say this | What it does |
|---|---|---|
| `start` | `/flow:start`, "where do I start?" | Checks your setup, explains the loop, proposes a first task |
| `orchestrate` | "deploy an agent", "same machinery", "you manage everything from here" | Runs the loop with implementer and verifier agents, three slots kept full |
| `grill-to-epic` | "/grilling ...", "q3 ..., agree with the rest", "file the epic" | Numbered questions with a recommendation each, then an epic with buildable sub-issues |
| `ship-pr` | "commit and push", "file the pr", "merge it", "close the issue" | Commit to merged PR with guards against a bad CI verdict or a stale branch |
| `smoke-test` | "make sure it's smoke tested", "how was it verified?" | Runs the real thing, signed in, both themes, evidence in the PR |
| `fresh-eyes` | "investigate without bias", "adversarial agent" | A clean-context agent re-diagnoses or tries to break the change |
| `status-report` | "how is it so far?", "whats next?", "what do you need from me?" | Fifteen lines in a fixed order, measured now |
| `overnight-handoff` | "I'm going to sleep", "you have the reins" | Clears blockers, records the mandate, queues work, writes the morning recap |
| `long-haul` | "/goal ...", "do not stop until it is done and verified", "how is the goal progress?" | Runs a goal for days or weeks: a checkable goal, one program note, wake-ups and watchers, scripts for chains and merge trains |
| `owner-scripts` | "what do I need to run?", "let me know what pastes are needed" | One paste per step, dry run by default |
| `save-state` | "can I compact this session?", "write this to memory" | State, grant and decision notes that survive compaction |
| `issue-sweep` | "any orphan issues?", "what can be merged?" | Closes done issues, lists mergeable PRs, ranks what is ready |
| `research-to-gist` | "deploy agents to research", "write it to a gist" | Parallel researchers, abstract first, sources, a secret gist |
| `data-anomaly` | "why is this value so high?", "why only 12,000?" | Traces a wrong number to the layer that produced it, fixes it there, repairs the rows |
| `accuracy-loop` | "do another round", "do not stop until all cases are covered" | Sample, check, fix, repeat on a larger sample until a stated target holds |
| `failed-run-triage` | "check all the failed ones and see what can be done" | Failures by cause, what can be retried, the command that reruns only those |
| `benchmark-on-budget` | "run the evals on X", "how does it stack up against Y" | Gold set, budget up front, cost per item, instances shut down |
| `long-run-cli` | "can it run faster?", "show progress", "what are the exact commands?" | Progress, resume, all cores, runbook in the same change |
| `ui-fix` | a screenshot with a complaint | Fix in place, tokens, both themes, phone and desktop |
| `repo-conventions` | "update the claude md", "instruct it to always ..." | AGENTS.md as the index, with a starter template and stack defaults |
| `retro` | "do a retro on those sessions", "how much of these concerns are valid" | Counts from the transcripts and the tracker, incidents by class, what to change |
| `cleanup` | "cleanup", "free up disk space" | Stops what it started, removes merged worktrees, reports disk |

Three agent definitions ship with it: `flow:implementer` (Opus, high effort), `flow:reviewer`
(Opus, xhigh, read-only) and `flow:verifier` (adversarial smoke tester). They carry the standing
rules, so a brief only has to say what is specific to the task.

Reference files worth reading on their own:

- `plugins/flow/skills/orchestrate/references/briefs.md`: fill-in briefs for four agent roles
- `plugins/flow/skills/orchestrate/references/traps.md`: what went wrong and the guard for each
- `plugins/flow/skills/orchestrate/references/shared-resources.md`: what a worktree does not
  separate (database, auth, sandboxes, env files, CI), with a lock script and a claims folder
- `plugins/flow/skills/ship-pr/references/git-traps.md`: squash, force push, stacked PRs, markers
- `plugins/flow/skills/long-haul/references/stalls.md`: what stalled nine multi-day runs, with the
  hours each cost
- `plugins/flow/skills/long-haul/references/keeping-going.md`: what survives a restart, wake-ups,
  watchers, and scripts for unattended chains, merges and the program note
- `plugins/flow/skills/repo-conventions/references/AGENTS.template.md`: a starter instruction file

## The `unslop` plugin

Writing rules that strip AI tells from replies, commit messages, PR bodies and docs, adapted from
the unslop skill in `cursor/plugins`. A hook repeats the short form on every prompt so the rules
survive context compaction. Set `UNSLOP_HOOK=0` to silence it for a session.

## What the skills lean on

They work alone. They work better with these, which `bootstrap/install.sh` installs:

- `code-review` and `mattpocock-skills` (for `/grilling`) from the official plugin marketplace
- `to-issues` and `to-prd` from `mattpocock/skills`
- `efficient-fable`, `quick-recap` and `stay-within-limits` from `@agent-native/skills`
- the `gh` CLI, signed in

The `full` profile reproduces my whole machine: 34 plugins and 39 third-party skills, listed in
`bootstrap/manifest.json`.

## Bootstrap

`bootstrap/install.sh` is dry run by default and safe to run twice.

- adds this marketplace and installs both plugins
- adds the third-party marketplaces, plugins and skills of the chosen profile
- writes `bootstrap/CLAUDE.global.md` into `~/.claude/CLAUDE.md` between two marker lines, keeping
  everything else in the file and making a backup

`--skip kit|unslop|plugins|skills|claude-md` leaves a group out. `--kit-source ciocan/claude-kit`
points Claude Code at GitHub instead of the checkout.

`bootstrap/CLAUDE.extras.md` holds rules I stated per project that are candidates for the global
file. The installer does not apply it.

The install commands for the `@agent-native` skills were taken from their READMEs and not run
while building this kit. If one fails, the log names it and the rest still install.

## Changing the defaults

- Models and effort per role: `plugins/flow/skills/orchestrate/references/models-and-limits.md`
  and the `model` and `effort` lines of the three agent files.
- Number of agents at once: the "Slots" section of `orchestrate`.
- Anything a repository decides for itself (merge style, who closes issues, branch names) belongs
  in that repository's `AGENTS.md`. The skills defer to it.

## Checking the kit

```sh
claude plugin validate .
claude plugin validate plugins/flow
claude plugin validate plugins/unslop
tests/long-haul.sh          # detached runs, chains and the merge train, against a stub gh
tests/shared-resources.sh  # lock.py and claims.py
tests/notes.sh             # note.py: stamped log entries, rotation
tests/tick.sh              # tick.py: issue checkboxes, against a stub gh
tests/retro.sh             # transcript-digest.py, against hand-written fixtures
tests/cited-paths.sh       # cited-paths.py: do the paths an issue cites exist on the base
tests/env-names.sh         # env-names.py: variable names of env files, never a value
```

## Releases

[release-please](https://github.com/googleapis/release-please) cuts the releases. On every push
to `main` it opens or updates a release pull request. Merging that pull request tags
`v<version>`, publishes the GitHub release, updates `CHANGELOG.md` and writes the same version
into both plugin manifests. A release and the plugins Claude Code installs carry one number.

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org).
- `feat` bumps the minor number. `fix`, `docs` and `refactor` bump the patch number. Below 1.0 a
  breaking change bumps the minor number too.
- `chore`, `ci`, `build`, `test` and `style` commits do not cut a release. Claude Code caches an
  install per version number, so never use one of those for a change under `plugins/`. Users
  would not receive it.
- Do not edit `version` in a plugin manifest by hand. The release pull request sets it.
- The repository must allow Actions to open pull requests: Settings, Actions, General, Workflow
  permissions, "Allow GitHub Actions to create and approve pull requests".

The config is `release-please-config.json`, the last released version is in
`.release-please-manifest.json`, and the workflow is `.github/workflows/release-please.yml`.

## Licence

MIT, see `LICENSE`. The `unslop` skill is adapted from pstack, also MIT. Its notice is in
`plugins/unslop/NOTICE.md`.
