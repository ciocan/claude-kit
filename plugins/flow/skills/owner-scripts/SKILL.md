---
name: owner-scripts
description: Hand the user a step that needs their own credentials, shell or approval as one script they can paste, dry run by default. Use when a command is refused by the permission classifier, needs a secret, a login, sudo or a production write the user has not delegated, and when the user asks "what do I need to run?", "tell me the exact commands" or "let me know what pastes are needed".
---

# Owner scripts

Some steps are the user's: a secret only they hold, a login in their browser, a write the
permission classifier refuses, a production change they kept for themselves. Make each of those a
single paste.

## Try first, hand over second

- When the user's grant covers the command, run it. Hand over only what is refused or reserved.
- A refusal is final for you. Do not retry it in another form, split it into smaller commands, or
  ask a subagent to run it. Hand the exact line over once and move on to other work.

## The script

Write `<topic>-owner.sh` somewhere that survives the session, under the repository's scripts
folder or a directory outside the scratchpad.

- `set -euo pipefail`, safe to run twice.
- Dry run by default. `--apply` acts.
- A preflight that checks the host, the checkout and the variables it needs, and fails with a
  sentence that says what is missing.
- It sets its own connection settings. A paste that depends on the user's shell state fails.
- It prints what it is about to do and what it did.
- It never prints a secret. Secrets come from the secret store or a prompt, and go to commands on
  stdin. Arguments show up in process lists and telemetry.
- A long run gets its own script and its own line. Never chain one in front of a migration.

## Handing it over

One line per step, in order:

```
1. ! bash /abs/path/migrate-123-owner.sh           dry run, prints the plan, about 5 s
2. ! bash /abs/path/migrate-123-owner.sh --apply   applies it, about 2 min, ends with "applied 3"
```

- The `!` prefix runs the line in the session, so the output lands in the conversation. No space
  after the `!`.
- Say what the output should look like and how long it takes.
- A prompt for a secret has no terminal behind `!` and stores an empty value. Tell the user to run
  those in their own terminal.
- When the user sends such a line as a normal chat message, they are asking you to run it.

## Afterwards

Check read-only that the step took effect, and record what ran and when in the state note. In the
recap, separate what you ran from what still waits for the user.

## The plain variant

For "what are the exact commands?", give a numbered list in order, each with its duration, what
it must print, and what has to be rebuilt afterwards.
