---
name: long-run-cli
description: Build or change long-running command-line tools (scans, backfills, batch fetches, migrations, ingests) so they show progress, resume after a stop, use the machine's cores and stay documented in the runbook. Use when writing or modifying a CLI verb, flag or env var, a batch job, a scraper or an indexer, and when the user asks "can it run faster?", "use all cores", "show progress" or "what are the exact commands to run?".
---

# Long-running CLIs

Anything that can run for more than a few seconds follows this contract.

## Progress

- Print one startup line at once: what the run does, how many items, where it resumes from. A tool
  that sits silent looks hung.
- Draw progress on stderr: a bar, done over total, an ETA, and live outcome counters (ok, skipped,
  failed). A run with several lanes shows a line per lane.
- Report an honest rate. Count the items that did work. Skips that cost nothing inflate the rate
  and wreck the ETA.
- When stderr is not a terminal, print a plain line every so often. A progress bar renders nothing
  through a pipe, and cron and systemd logs need lines. Offer `--progress auto|live|plain`.

## Stop and resume

- Checkpoint as you go and make reruns idempotent. A second run picks up where the first stopped.
- Ctrl-C prints the command that resumes.
- Work incrementally by default. A full rescan is a flag, not the normal path.
- Anything that writes has `--dry-run`. Add `--status` when a run can be inspected from outside.

## Speed

- Use the cores. Partition the input, size the worker pool from the CPU count with a flag to
  override, keep one writer. A single-core phase on a large machine is a defect.
- Keep checkpoints working under parallel runs, and add a test that the parallel output equals the
  serial one.
- Concurrency, proxy choice and rate limits are flags or config. Changing them never needs a code
  change.
- When asked to make something faster, read the code for what can overlap before answering, offer
  the parallel form first, and report wall-clock time before and after.

## Runbook, in the same change

A command, flag, default or env var that changes updates the operational runbook in the same
change: the command signature, any setup step (new env vars, secrets, binaries), what it means
for the schedule, and how to recover. The feature is not done until the runbook says so. When the
runbook grows past comfortable reading, split it by topic and keep an index.

## "What do I run?"

Answer with a numbered list of commands in order, ready to paste, each with its expected duration
and what its output should show. Say what must be rebuilt or reindexed after the change.

## Stack defaults

- Python: uv, hatchling, `src` layout, argparse subcommands, httpx, rich on
  `Console(stderr=True)`, pydantic v2, python-dotenv, ruff, pytest.
- Go and Rust: one internal progress package with the same contract, used by every command.
- When a port needs an outside tool (OCR, PDF, geocoding, parsers), look at the options native to
  the language before shelling out to the old one.
