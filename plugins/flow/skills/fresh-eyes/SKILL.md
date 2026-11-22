---
name: fresh-eyes
description: Re-investigate a problem or verify a change with an agent that has clean context and none of the earlier conclusions, then compare its findings with the first diagnosis. Use when a fix did not hold, a bug came back, the user doubts a diagnosis or asks "how was it verified?", or says "investigate without bias", "start fresh", "fresh context", "deploy another investigator", "adversarial agent" or "run a few rounds of verifiers".
---

# Fresh eyes

The agent that built a fix believes in it, and the session that wrote a diagnosis keeps finding it
confirmed. A second agent with none of that history is the cheapest way to find out who is right.

## When to use it

- a fix shipped and the symptom is still there, or came back
- the same agent built the change and declared it verified
- the function is one where a miss is expensive: redaction of personal data, money, access checks,
  anything that deletes

## The investigator brief

Give the symptom and the access, nothing else.

- Include what was observed, where, the steps or the record that reproduces it, and how to reach
  the data or the running system.
- Leave out the issue's analysis, the earlier fix, your theory and the names of the files you
  suspect.
- Ask for the root cause with evidence, the edge cases around it, how to verify a fix, and what
  the agent did not check.

## The adversarial verifier brief

- Include the acceptance criteria and the diff or the branch.
- Leave out the implementer's account of what it tested.
- Ask the verifier to try to break the change: inputs the author did not think of, the unhappy
  paths, the state left behind after a failure. It also runs the real thing, see `smoke-test`.
- Ask it to name one assumption its checks share with the implementer's tests (the same payment
  method, account type, fixture or locale) and to break that one.
- For the expensive functions above, run several rounds, each with a new agent, until a round
  finds nothing.

A fresh agent has new eyes on the code and the same acceptance criteria as everyone before it. A
case the criteria never mention survives any number of rounds. That gap is closed earlier, by the
failure-mode pass in `grill-to-epic`, and later, by one review of the merged whole (`orchestrate`).

## Comparing

- Where the two accounts agree, the finding is probably real.
- Where they differ, settle it by reproducing, never by counting votes or by which report reads
  more confident.
- Tell the user both diagnoses and which one the evidence supports.

## Answering "how was it verified?"

Answer with the commands that ran and what they printed. If the environment could not check
something, say so in those words: no live data here, no signed-in session, no access to the
cluster. Never report numbers as verified when nothing could measure them.
