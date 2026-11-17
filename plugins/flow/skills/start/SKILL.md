---
name: start
description: Onboard someone new to the flow plugin in their own repository. Check the prerequisites, read how the repository is set up, explain the loop in a few lines and propose one small first task to run through it. Use when the user runs /flow:start, says they just installed flow or claude-kit, or asks "how do I use flow?", "where do I start?", "what can I say?" or "what does this plugin do?".
---

# Start

The user is new to this plugin. Get them from install to a first merged pull request with as
little reading as possible: check, report, explain, propose. Do not start any work in this skill.
The whole answer fits in about forty lines.

## 1. Check, read-only

Run these together. Keep the raw output to yourself.

- `git rev-parse --show-toplevel` and `git remote -v`: a repository with a GitHub remote
- `gh auth status`: the GitHub CLI is signed in
- `gh repo view --json defaultBranchRef` and `git branch -r`: the default branch, and whether a
  separate integration branch such as `dev` exists
- `AGENTS.md` and `CLAUDE.md` at the root: present, and do they name gate commands (lint, types,
  tests, build)
- `.github/workflows/`: is there CI, and which commands does it run
- `gh issue list --limit 10`: is there a backlog to pick from
- this session's skill list: are `code-review` and a grilling skill installed

## 2. Report

One line per item, ready or missing. For each missing item give the one thing that fixes it.

| Missing | Fix to offer |
|---|---|
| not a git repository, or no GitHub remote | stop here and say so. The loop needs both |
| `gh` not signed in | run `gh auth login` in a terminal |
| no instruction file, or one without gate commands | say "set up AGENTS.md for this repository with the house conventions" |
| no CI | not a blocker. Say that merges will rest on the local gates alone |
| no `code-review` plugin | `/plugin install code-review@claude-plugins-official` |
| no grilling skill | `/plugin install mattpocock-skills@claude-plugins-official` |

## 3. Explain the loop

Five lines at most. One session orchestrates and does not write code. Each unit of work goes
issue, worktree, implementer agent, reviewer agent, smoke test, pull request, merge. Done means
reviewed and run for real. Nothing is committed, pushed or merged without the user's word.

## 4. Give the phrases

List these eight, each with what it does in a few words:

- "deploy an agent to fix X"
- "you manage everything from here"
- "work here, no branch"
- "how is it so far?"
- "what do you need from me?"
- "how was it verified?"
- "merge it and close the issue"
- "cleanup"

## 5. Propose a first task

- Pick the smallest open issue that looks self-contained and name it. With no backlog, ask for a
  small bug they already know about.
- Give the exact prompt to send, with the grant sentence included:
  "deploy an agent to fix #<n>. when it is verified and smoke tested, file the pr. you have
  permission to commit and push for this."
- Say what it costs: one unit of work runs three agents, so start with one before running a wave.
- When the instruction file is missing, propose that step first. An agent without gate commands
  guesses.

## Rules

- Do not launch agents, edit files or create issues here. Wait for the user to pick.
- Skip what is already in place. Do not explain a tool they evidently use.
- If they asked one specific question ("what can I say?"), answer that part only.
- Close with the link to the full walkthrough:
  https://github.com/ciocan/claude-kit/blob/main/docs/guide.md
