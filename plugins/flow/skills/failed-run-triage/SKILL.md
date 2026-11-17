---
name: failed-run-triage
description: Sort the failures of a batch run by cause, say which can be retried and which are dead, fix the cause and give the command that reruns only what failed. Use when the user says "check all the failed ones and see what can be done", "there are errors in the run, could you check?", "why did it fail and why was it not caught?", or when a long job ends with failures or an unexpected count.
---

# Failed-run triage

## 1. Read the failures, not the summary

Open the failure log or the failed records. Count by error. Then sort into causes:

| Cause | Looks like | Retry? |
|---|---|---|
| Transient | timeouts, dropped connections, rate limits, a proxy that failed | yes, with backoff |
| Source | an endpoint down, an empty body, a format that changed | after the source is back or the parser is fixed |
| Data | a malformed record, a shape nobody planned for | after the code handles it, or never |
| Code | an exception in your own logic | after the fix |
| Resource | out of memory, disk full, GPU exhausted | after the limit is raised or the batch is smaller |

For each cause give the count, two or three examples, and whether it can be retried.

## 2. Check for failures that did not fail

- A source that answers 200 with an empty body counts as a success in most logs. Probe a record
  you know has content before trusting "empty".
- A run can exit 0 having done nothing. Compare the count it processed with the count it was
  given.
- Records that errored are often cached as done. A rerun then skips them.

## 3. Fix the cause

- Code: a test from the failing record, then the fix.
- Data: handle the shape, or quarantine the record with the reason written down.
- Transient: a retry policy with backoff. When the source blocks the run, pause and resume by
  itself. Do not push through with more concurrency. The source's capacity is the ceiling.
- Resource: a smaller batch, a limit, or a machine that fits.

## 4. Rerun only what failed

Give the exact command for the failed set. Delete cached error records first. Afterwards compare
the failed count before and after, and list what is still dead with the reason for each.

## 5. "Why was it not caught?"

Name the check that was missing: a test, a validation of the input, a count compared at the end,
an alert, a smoke on a sample large enough to meet the shape. Add it in the same change.

## Report

A table of cause, count and action. The rerun command. What is dead and why. How long the rerun
takes, from the measured rate.

## Rules

- Never rerun everything to hide a failure rate.
- An interrupted run resumes from its checkpoint. If it has none, that is the first fix
  (`long-run-cli`).
- When the first explanation does not hold, send an investigator with a clean context
  (`fresh-eyes`).
