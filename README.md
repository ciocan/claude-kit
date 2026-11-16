# claude-kit

How I run Claude Code, packaged so it works on another machine or for another person. Two
plugins and a bootstrap script.

The skills were distilled from about 6,000 of my own prompts across 26 projects and 76 feedback
notes that Claude recorded when I corrected it. Each skill answers a request I typed dozens of
times, and each trap in the reference files cost a lost branch, a dead shell or a full disk at
least once.

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

## The `flow` plugin

One loop, the same for every unit of work: issue, worktree, implementer, fresh reviewer, smoke
test, PR, merge, close. The main session orchestrates and stays out of the code.

| Skill | Say this | What it does |
|---|---|---|
| `orchestrate` | "deploy an agent", "same machinery", "you manage everything from here" | Runs the loop with implementer and verifier agents, three slots kept full |
| `grill-to-epic` | "/grilling ...", "q3 ..., agree with the rest", "file the epic" | Numbered questions with a recommendation each, then an epic with buildable sub-issues |
| `ship-pr` | "commit and push", "file the pr", "merge it", "close the issue" | Commit to merged PR with guards against a bad CI verdict or a stale branch |
| `smoke-test` | "make sure it's smoke tested", "how was it verified?" | Runs the real thing, signed in, both themes, evidence in the PR |
| `fresh-eyes` | "investigate without bias", "adversarial agent" | A clean-context agent re-diagnoses or tries to break the change |
| `status-report` | "how is it so far?", "whats next?", "what do you need from me?" | Fifteen lines in a fixed order, measured now |
| `overnight-handoff` | "I'm going to sleep", "you have the reins" | Clears blockers, records the mandate, queues work, writes the morning recap |
| `owner-scripts` | "what do I need to run?", "let me know what pastes are needed" | One paste per step, dry run by default |
| `save-state` | "can I compact this session?", "write this to memory" | State, grant and decision notes that survive compaction |
| `issue-sweep` | "any orphan issues?", "what can be merged?" | Closes done issues, lists mergeable PRs, ranks what is ready |
| `research-to-gist` | "deploy agents to research", "write it to a gist" | Parallel researchers, abstract first, sources, a secret gist |
| `benchmark-on-budget` | "run the evals on X", "how does it stack up against Y" | Gold set, budget up front, cost per item, instances shut down |
| `long-run-cli` | "can it run faster?", "show progress", "what are the exact commands?" | Progress, resume, all cores, runbook in the same change |
| `ui-fix` | a screenshot with a complaint | Fix in place, tokens, both themes, phone and desktop |
| `repo-conventions` | "update the claude md", "instruct it to always ..." | AGENTS.md as the index, with a starter template and stack defaults |
| `cleanup` | "cleanup", "free up disk space" | Stops what it started, removes merged worktrees, reports disk |

Three agent definitions ship with it: `flow:implementer` (Opus, high effort), `flow:reviewer`
(Opus, xhigh, read-only) and `flow:verifier` (adversarial smoke tester). They carry the standing
rules, so a brief only has to say what is specific to the task.

Reference files worth reading on their own:

- `plugins/flow/skills/orchestrate/references/briefs.md`: fill-in briefs for four agent roles
- `plugins/flow/skills/orchestrate/references/traps.md`: what went wrong and the guard for each
- `plugins/flow/skills/ship-pr/references/git-traps.md`: squash, force push, stacked PRs, markers
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
```

## Licence

MIT, see `LICENSE`. The `unslop` skill is adapted from pstack, also MIT. Its notice is in
`plugins/unslop/NOTICE.md`.
