---
name: benchmark-on-budget
description: Compare models, OCR engines or pipeline variants on a fixed gold set under a stated budget, and report accuracy, latency and cost per item with a recommendation. Use when the user asks to "run the evals on X", "see how it stacks up against Y", "benchmark against", wants to compare extraction or OCR quality, or needs a full run on rented GPUs sized to a deadline and a budget.
---

# Benchmark on a budget

## Before spending anything

- State the budget and the deadline. If the user gave none, ask for both.
- Estimate the cost of the run and say it before starting. Ask again before going over.
- Fix the gold set, the prompts and the number of runs per candidate. Three runs or more when the
  output varies between runs.
- Name the baselines: what runs in production today, and one commercial product when the user
  wants to know whether building beats buying.

## The projection

Before a long or paid run, measure the rate on a small sample and state three figures: hours for
the whole corpus, cost, and the same for one or two other fleet sizes. For a hosting bill, give
the cost at three traffic levels from the measured cost per request.

## Running it

- Enforce the output schema with structured outputs. A free-text answer parsed afterwards measures
  the parser.
- Try a handful of items through a hosted API first. Batches of more than a few hundred items go
  to reserved or self-hosted capacity. A pinned provider's throughput is the ceiling, and adding
  lanes past it only raises latency and errors.
- Records that errored are often cached as done. Delete them before a retry.
- Measure proportions of a corpus with aggregations. Random sampling in a search index can return
  a set that looks nothing like the corpus.
- One candidate per agent, in parallel within the usage limits. Give each agent its own output
  directory.

## What to record per candidate

- score, overall and per category
- the failures, listed, with two or three examples each
- latency at the median and at the 95th percentile
- cost per item and for the full corpus, with the token counts behind it

## The report

A table, then conclusions and a recommendation, then what was not tested. Put the technical
version in the repository's docs, on a branch and never loose in the user's checkout
(`save-state`). Write a shorter version for a non-technical reader when asked.
`research-to-gist` covers delivery.

## Sizing a full run

Measured throughput gives the number of instances needed to finish by the deadline, and that
gives the cost. Say both. When the credit on the account does not cover it, ask for the top-up
before starting, never in the middle.

## Rented instances

- A name prefix per project, and a time to live on every instance.
- Model weights on a persistent volume, and an install script for a new instance.
- When several agents share one account, check which workspace is active before each command.
- Pin the provider and the quantization when comparing hosted models. The same model name serves
  different builds.

## Evals of your own agent

When the product contains an agent, every change to its prompts, tools or model reruns the eval
set and must score at least as well as the previous run. Report the cost per answer as well. To
find out why one production session went wrong, read its transcript: where it stalled, what it
invented, which tool failed.

## At the end

Shut down every instance you started and confirm the count is zero. Sweep sandboxes and scratch
output. Say what was cleared and what the run cost in total. See `cleanup`.
