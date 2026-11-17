---
name: data-anomaly
description: Trace a number that looks wrong to the layer that produced it, count what is affected, fix it at the source and repair the existing rows. Use when the user points at a figure, a total or a record and asks "why is this value so high?", "why do 2023 and 2024 have the same number?", "why only 12,000?" or "why does this company show under another name?", pastes the URL of a page with a suspicious value, or asks to audit one dataset against another.
---

# Data anomaly

A wrong number on a page is rarely a bug in the page. The page shows what the data layer gave it.
Fix the layer that produced the value, then the rows it already wrote, and only then the display.

## 1. Pin it down

- Reproduce with the exact record or query the user saw. Write the query down.
- Check freshness before correctness. A total can be stale because a projection or a rebuild is
  hours behind. Compare the timestamp of the data with the source.

## 2. Walk the layers backward

Look at the same record in each layer, from the page back to the raw source: page, API, serving
store or index, transform, ingest, source file. The first layer where the value is wrong owns the
bug.

When the source itself is wrong, say so. Then decide with the user: flag the record, exclude it,
or keep it with a note. Do not silently correct a public source.

## 3. Size it

- Count the affected rows with an aggregation, grouped by cause. A random sample from a search
  index can look nothing like the corpus.
- Look for the class, not the instance. The same defect usually has siblings: values off by
  orders of magnitude, the same figure repeated across years, a unit or currency mixed up, a name
  resolved to the wrong entity, a field left empty that can be recovered from another.

## 4. Fix at the source

- Change the layer that owns the bug, with a test built from the real case. Mint the identifiers
  in the fixture. No real person's data in a test.
- If two layers share the contract, fix both sides in one change.

## 5. Repair what is already written

- Give the command that repairs the existing rows, with a dry run that prints counts.
- Production applies follow the user's grant (`owner-scripts` when they are not yours to run).
- Run the aggregation from step 3 again. It should return zero, or the rows left by design.

## 6. Report

The cause in one sentence, the layer, the rows affected before and after, the repair command, and
what stays as it is on purpose. Post it on the issue when one exists.

## Auditing one dataset against another

- Count both sides, then the records in one and not the other, in both directions.
- Group the mismatches by cause. Most fall into three or four groups.
- Produce a worklist for the cases only a person can settle.
- Start with the cheap deterministic checks. Bring a model in for what they cannot decide.

## Rules

- Never print personal data or real identifiers while investigating. Select counts.
- Where the environment has no live data, say "could not verify here" and give the query to run.
- When the first diagnosis does not hold, send an investigator with a clean context (`fresh-eyes`).
- A guard on the display (hide or flag an implausible value) comes after the fix, never instead.
