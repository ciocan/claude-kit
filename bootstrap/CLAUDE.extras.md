# Rules worth promoting to the global file

These rules were stated in one repository at a time and recorded in that project's memory. Each
one came up in at least two projects. The installer does not apply this file. Copy the ones you
want into `~/.claude/CLAUDE.md`.

# autonomy
- Use your best recommendation and ask me only for bigger strategic decisions: what the product
  promises or sells, money outside the usual run costs, a change of architecture or of a data
  store, anything that drops data or cannot be undone, anything that reaches people outside the
  team. For the rest, act, then say in the recap what you did and what I can overrule.

# orchestration
- In an orchestrated session the main thread does not code. It dispatches agents, verifies what
  comes back, and handles git, PRs and issues. I will say "work here" when I want it inline.
- The strongest model orchestrates and does the closing review. Implementers run one tier below
  at high effort, reviewers one tier below at xhigh. A model I name for a task wins. Do not use
  the small model to implement or review unless I ask.
- Keep three agent slots full. When one frees, start the highest-impact unblocked item and tell
  me which and why.
- Done means verified and smoke tested in the running app, by an agent that did not write the
  change.

# language
- Everything in code is English: identifiers, file names, comments, test titles, commit
  messages, docs. Only text the user reads is in the product's language.
- Answer me in English.

# issues
- Close an issue yourself once merged PRs meet all its acceptance criteria. Post one comment that
  maps each criterion to a PR.
- Check that an issue is not already done before briefing an agent on it.

# shared machine
- Never stop or restart a dev server you did not start. Run smoke tests on another port.
- Long stages use every core. A single-core phase on a large machine is a defect.
