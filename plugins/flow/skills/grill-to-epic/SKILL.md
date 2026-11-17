---
name: grill-to-epic
description: Turn a design discussion into buildable work. Ask numbered questions with a recommendation each, record the decisions, then file an epic with vertical-slice sub-issues that agents can pick up. Use when the user runs /grilling or /grill-me on a feature, answers with "q3 ..., agree with the rest", or says "file the epic", "create the detailed epic and sub-issues", "draft the issues" or "agree with all, let's build it".
---

# Grill to epic

A grilling session ends in decisions. This skill covers how to ask so the user can answer in a few
words, and how to turn the answers into issues an agent can build without the conversation.

## Asking

- Read the code and the docs first. Never ask what the repository already answers.
- Number the questions `q1` to `qN`. Give each one lettered options with the recommended option
  first and marked, one line of reasoning, and the alternatives you rejected.
- Lead with the recommendation. An open "what do you think?" slows the session down. Ask only
  where a real branch exists that the user must choose. Decide the rest yourself and list those
  choices as assumptions.
- Expect terse answers: "a", "agree", "q3 Bun only, q4 native sql, agree with the rest". "Agree
  with the rest" accepts every recommendation that was not overridden.
- When the user corrects a number or a fact, update and move on. No defence, no recap.
- Stop when a round produces no new branch.

If a `grilling` skill is installed, it runs the interview. Apply the question format above to it.

## Recording

- Write the decisions where the repository keeps them: `docs/decisions/`, an ADR, or a PRD under
  `docs/`. Each entry holds the decision, the reason, and what was rejected.
- Some designs end in a document. When the user asks for a design doc or an implementation plan,
  write that, with the reasoning for each section, and stop. File issues only when asked.
- When the user wants to see it first ("show me a few variants before building"), produce a mock or
  an artifact with variants before any issue is filed.

## Filing

- The epic issue holds the goal as a checkable end state, a summary of the decisions, what is out
  of scope, and an ordered checklist of sub-issues.
- Each sub-issue is a vertical slice that can be built and verified alone. It carries context,
  acceptance criteria, the smoke test (what to run or which screen to walk, and what it must show),
  its blockers by issue number, and the files it will probably touch.
- Give the epic and its sub-issues one shared label so they list together.
- Write each sub-issue so the implementer does not have to guess.
- Plan in phases and agent runs. No estimates in human weeks, and no calendar unless asked.
- Mark which slices can run in parallel. Those form the waves.
- Ask once how the work should land: one PR per issue, or one branch and one PR with a commit per
  sub-issue. Frontend epics often take the second form.

If a `to-issues` skill is installed, use it for the slicing.

## Handing over

- Offer a goal line for `/goal`. One sentence, a state someone can check: "complete epic 980,
  everything verified in both the browser and the API". `long-haul` covers how to word it and
  how to run it for days.
- On "deploy agents to work on the epic", switch to `orchestrate`.
- As slices land, post progress and build notes as comments on the epic. The epic is the record
  for anyone who was not in the session.
