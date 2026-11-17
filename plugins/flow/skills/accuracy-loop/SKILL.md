---
name: accuracy-loop
description: Raise the accuracy of an extraction, classification or parsing pipeline in rounds. Sample, check against a gold set or the source, fix the schema, prompt or rule, and repeat on a larger sample until a stated target holds. Use when the user says "do another round", "check 500 more and fix what you find", "do not stop until all cases are covered", asks "how do we make sure every document is covered?", or sets a coverage or accuracy target for a pipeline.
---

# Accuracy loop

Each pass over real documents finds shapes the last one missed. The loop ends on a measured
target, not on a round that felt clean.

## Before the first round

- **The target.** A number and what counts as an error, per field: 0.99 of documents with every
  required field correct, for example. Ask when the user gave none.
- **The gold set.** Build it and have a person validate it before trusting any score. For a few
  hundred items, give them a small page to adjudicate on. A second model's verdict on a gold item
  is a lead for the person, not a ruling.
- **A held-out part.** Keep some gold items out of every fix. Score on those.

## One round

1. Sample at random from documents no round has seen. Stratify by year, type and source, so the
   rare shapes turn up.
2. Run the pipeline. Compare with the gold set or with the source document.
3. List the misses grouped by cause, with two examples each.
4. Patch the schema, the prompt or the rule. One cause, one patch.
5. Rerun the misses, and the regression set made of every earlier fix.
6. Record the round: the version of the schema or prompt, the sample size, misses by cause, the
   figure reached.

Grow the sample each round: 100, then 500, then more. Have a fresh agent do the checking. The one
that wrote the patch finds it correct (`fresh-eyes`).

## When to stop

- The target holds on the held-out items, and the last round found no new cause.
- The sample was large enough to say so. With no miss in `n` documents, the miss rate can still be
  as high as about `3/n`. A clean round of 300 supports "under 1 percent" and nothing stronger.
- When the target cannot be reached by rules or prompts, say so with the figures, and propose
  what is left: a list for a person to review, or a lower target.

## At corpus scale

- Project the time and cost of a full pass before starting one (`benchmark-on-budget`).
- After a patch, rerun only the documents it can affect.
- Records that errored are often cached as done. Delete them before a retry.
- Deterministic checks first. A model for what they cannot decide. A worklist for what the model
  cannot.
- Enforce the output schema with structured outputs.

## Rules

- Never score on items you tuned on.
- A fix for one shape must not break another. That is what the regression set is for.
- Keep the record of rounds in the repository. It is the evidence that the target was met.
- An unattended loop ("do not stop until all cases are covered") still needs the stop rule above,
  and a bound on rounds or spend.
