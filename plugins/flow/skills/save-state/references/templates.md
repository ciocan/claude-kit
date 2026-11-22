# Note templates

All three are memory notes. Give each a kebab-case file name and add a one-line pointer to it in
the memory index.

## State note

```markdown
---
name: <epic-or-goal>-<n>-<slug>-state
description: "<epic ref> <title>: <one-line status, k of n merged, open PRs, who owes what>"
metadata:
  type: project
---

<Epic ref> (<sub-issues>): <what it delivers>. Filed <date> from <source>.

Delivery: <one PR per issue | one branch, a commit per sub-issue>, base <branch>, worktrees under
<path>. Method: implementer per worktree on <model>, reviewer on <model>, <who commits>.
Waves: <A = ...; B = ... after ...>.

**Why:** <what a later session must not reopen>.
**How to apply on resume:** read the tail of this log, `gh issue view <epic>`, `git log`, restart
<queue or monitor> with <command>. Related: [[<grant note>]], [[<decision note>]].

## State log
- <YYYY-MM-DD HH:MM UTC>. Main at <sha>, deployed to <where>, smokes <pass | fail and cause>.
  Merged: #<pr> (#<issue>, <one-line effect>).
  In flight: #<issue> <agent id> <worktree> <branch> <head sha> <fix round R | review R | ready>.
  Review files waiting: <path> for <agent id>.
  Long runs: <job> <progress> ETA <time>, log <path>, resume with <exact command>.
  Owed after merge: <migration | rebuild | redeploy>.
  Queue when a slot frees: #<n>, #<n>. Blocked: #<n> on <reason>.
  User owes: <decision | paste | secret>, in order.
  Worktrees to remove after merge: <list>.
  Trap learned: <one line>.
- <YYYY-MM-DD HH:MM UTC>. DONE. Merged <list>. Open by design: #<n> (<reason>). User owes: <list>.
  Cleared: <worktrees, servers, containers>. Host: <disk free>.
```

Take every stamp in the log from `date -u`, never from memory. `note.py add` in `long-haul`
writes the entry heading for you.

## Rule or grant note

```markdown
---
name: <topic>-<date>
description: "User <date time UTC>: '<short quote>'. <what it allows or requires>. <scope>"
metadata:
  type: feedback
---

On <date> at <time UTC>, while <context>, the user wrote: "<exact words>".

Covers: <what I may now do, or must now do>.
Does not cover: <what stays theirs>.
Lasts: <this night | this epic | until revoked>. Replaces [[<older note>]].

My reading of "<unclear word>", which is mine and not their words: <interpretation>.

Limits that stay: a permission refusal is a separate gate, hand the exact line over once and do
not work around it. Destructive or irreversible steps still get a confirmation.

**Why:** <the cost they wanted removed>.
**How to apply:** <what changes in the loop>. Related: [[...]].
```

## Decision note

```markdown
---
name: decisions-<topic>-<date>
description: "Decisions of <date> on <topic>: <the two or three that matter most>"
metadata:
  type: project
---

Asked <date time UTC> after <what raised the questions>.

- [user] <question>. Chosen: <option>. Consequence: <code change | new issue #n | order of work>.
- [user] <question>. Chosen: <option>. Rejected: <option>, because <reason>.
- [session] <ruling taken alone>. Reason: <one line>. Overrule by: <how>.
- [session, kept class: <money | legal text | privacy | security | production>] <what I
  recommend>. Not decided. Waits for the user.
- Approved in advance: once <condition>, run <steps> without asking again.

Tag every line when you write it. In one log 82 of 107 rulings carried no tag and had to be
attributed afterwards.

**How to apply:** <which issues or briefs these bind>. Related: [[...]].
```
