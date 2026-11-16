# git
- **Never commit.** Do not run `git commit` or `git push` in any project unless I ask for a commit
  in the current conversation. Leave changes in the working tree. I review, commit and test
  myself. A grant I give for one repository or one goal does not carry to the next.

# documentation
- **The runbook stays current with the CLI.** Whenever a CLI command, verb or flag is added, or
  its behaviour, defaults or env vars change, update the project's operational runbook (for
  example `docs/runbook.md`) in the same change: the command signature, any setup step (new env
  vars, secrets, binaries), what it means for the schedule, and recovery notes. A feature is not
  done until the runbook reflects it. Same bar as the README and the architecture docs.

# CLI ergonomics
- **Every long-running CLI or script we build shows progress.** Anything that can run more than a
  few seconds (scans, backfills, batch fetches, migrations, ingests) gets a progress bar on
  stderr with done over total, an ETA and live outcome counters, plus a one-line startup summary
  at once (what it does, how many items, the resume point), so it never sits silent. Fall back to
  plain periodic stderr lines when stderr is not a terminal. Ctrl-C prints how to resume when the
  tool is checkpointed.

# writing
- **Use the `unslop` skill on every interaction.** It applies to all prose you write or edit:
  chat replies, commit messages, PR and issue bodies, docs, code comments, and the briefs you
  hand to subagents. Read the full skill before any substantial piece of writing.
- Fast pass, no exceptions: no em dashes (a period or a comma, and parentheses are not a legal
  swap), no opening praise and no closing "Let me know if...", delete "It is important to note
  that" and turn "In order to" into "To", no bold-label-colon bullets that restate the line, cut
  any sentence that would fit another project's docs unchanged.
- Never rewrite code identifiers, quoted user or UI text, cited sources, or existing prose you
  were not asked to touch.
- Pass "follow the unslop skill" into any subagent that produces text a human will read.

# working style
- When operating on the strongest and most expensive model, use the `efficient-fable` or
  `efficient-frontier` skill: orchestrate from the main session and send bounded work to cheaper
  subagents.
- End every response that completes a unit of work with the `quick-recap` status line.
- When long-running or parallel work is in flight, use the `stay-within-limits` skill and check
  usage between waves.
- For the loop from issue to merged PR, follow the `flow` plugin: `orchestrate`, `ship-pr`,
  `smoke-test`, `save-state`.

# cleanup
- **Clear what you started when a run is done.** After any eval chain, benchmark, dev-server or
  agent session: stop the servers you started, remove sandboxes, containers and the worktrees you
  cut for a one-off, shut down rented instances, and check `df -h /` before and after. Never
  leave this for me. Say in the recap what was cleared.
