---
name: research-to-gist
description: Run a research question with parallel agents and deliver a written report with evidence, an abstract first, the details after, comparison tables and sources. Use when the user asks to research pricing, competitors, a market, a brand name, a tool or stack choice, or says "deploy agents to research", "do a deep research", "write it to a gist", "write the report in a gist" or "argue for pros and cons".
---

# Research to gist

## Running the research

1. Split the question into angles that do not overlap: one per market, per competitor group, per
   candidate tool. Send one researcher per angle, at most three at a time.
2. Each brief asks for the whole report as the agent's final message, with a link for every claim,
   the date of each figure, and a list of what could not be verified. Subagents cannot write report
   files, so do not ask for one.
3. Do not put your expected answer in the brief. An agent handed a hypothesis returns it confirmed.
4. Reopen the sources behind any claim the recommendation rests on. Agent reports are leads.

## Shape of the report

- Abstract first, five to eight lines a busy reader can stop after: the question, the answer, the
  recommendation.
- Then the details: method, a comparison table, findings per angle, what stayed uncertain, sources.
- Conclusions and recommendations close the document.
- Pricing and competitor work gets one table row per provider and plan, with the date checked and
  the features the user asked about.
- Naming work states for each candidate which checks ran (domain, trademark registers) and which
  were blocked. An unchecked name is not an available name.
- Tool and stack choices argue both sides. When asked to "argue against" the favourite, do it
  honestly.
- On request, write a second, shorter version for a non-technical reader.

## Delivering

- Create the gist when the user asked for one. Otherwise put the report in the session and offer.
- `gh gist create <file> --desc "<title>"` makes a secret gist. Never pass `--public` unless told.
- A secret gist is unlisted, not private. Anyone with the URL can read it. Keep out hostnames,
  security findings, stack internals, customer data and anything that must stay secret.
- Later additions go to the same gist as a revision or a comment, so the URL stays the one the
  user already shared.
- Save a memory note of type `reference` with the gist URL, the date and one line on what it
  holds, so a later session finds it.
- Close by proposing the next step, usually an epic built from the findings. See `grill-to-epic`.
