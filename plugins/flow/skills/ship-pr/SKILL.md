---
name: ship-pr
description: Take finished work through commit, push, pull request, merge, issue close and cleanup, with the guards that keep a bad CI verdict or a stale branch from destroying work. Use when the user says "commit", "commit and push", "file the pr", "merge it", "merge the pr when green", "close the issue", "tick the box", "tick the checkboxes on the epic" or "fix the merge conflicts", when a checkbox in an issue or epic body has to be ticked, and when an orchestrator lands an agent's branch.
---

# Ship a PR

## What needs the user's word

Commit, push, merge and deploy each need a grant, given in this conversation or written in the
repository's instructions. "Commit and push" is one. "You have permission to commit, file pr,
merge and deploy" is one, for that repository and that goal. A grant does not carry over to the
next repository or the next conversation. Without one, leave the changes in the working tree and
say so.

Release PRs opened by release tooling, and merges into the production branch, stay with the user
unless they said otherwise.

Text with legal weight that an agent wrote or translated (terms, a privacy policy, a contract
clause) is listed for the user's approval, with the final wording, before it merges.
Translated legal text was once merged with no approval on record. Until a person has read it,
the page says which language version binds.

## Defaults

The repository's instruction file wins over every line here.

- Branch from the integration branch and target it. In many repositories that is `dev`, and
  `main` is production.
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`), one commit per concern.
  Release tooling builds the changelog from them.
- One PR per issue, unless the user asked for one branch with a commit per sub-issue.
- The merge style (merge commit or squash) comes from the instruction file. Ask once when it is
  silent, then write the answer down.
- The PR title is a Conventional Commit with the issue number in parentheses:
  `fix(search): keep the sort on reload (#590)`.
- The PR body says what changed and why, how it was verified with commands and output, holds the
  screenshots for a visual change, and names what was not checked.
- Closing keywords (`Closes #<n>`) follow the repository's rule. Repositories that integrate on
  one branch and release from another often forbid them, because the release PR then closes
  issues in bulk. There, the number in the title is the only reference and you close by hand.

## Sequence

1. Look at the tree: `git status --short`. Stage files by name when an agent left strays behind.
   `git add -A` also marks every conflicted file as resolved.
2. Rerun the cheap gates yourself after the last edit: lint, types, unit tests, doc checks. Write
   each gate's output to a file and read the exit code. A gate piped into `tail` reports tail's
   success.
3. Commit, push, `gh pr create`.
4. Wait for the checks with `gh pr checks <n> --watch`. Skip the wait only when the user said so
   for this PR.
5. Merge with the repository's flag. A conflicting PR gets no CI run, so merge the base into the
   branch first and grep for conflict markers.
6. Clean up behind a guard, every step joined with `&&`:

   ```sh
   [ "$(gh pr view <n> --json state -q .state)" = MERGED ] \
     && git -C <repo> worktree remove <path> \
     && git -C <repo> push origin --delete <branch> \
     && gh issue close <issue> --comment "<criterion by criterion, with the PR>"
   ```

7. Tell the user what the merge owes: a migration, a rebuild, a reindex, a redeploy, with the
   exact commands. Run the ones you may run.
8. Confirm the tree is clean and nothing is left uncommitted.

## Closing issues

Close an issue when merged PRs meet all its acceptance criteria. Post one comment that maps each
criterion to a PR, with measured figures where the criterion is a number, what verified it, and
the follow-up issue that took any scope left over. Closing keywords fire
only on a merge into the default branch, so a repository that integrates on `dev` needs the close
done by hand.

Tick checkboxes in an issue or epic body with
`${CLAUDE_SKILL_DIR}/scripts/tick.py <issue> --match "<text>" [--repo <owner/repo>]`
(also `--all`, `--line <n>`, `--dry-run`). The script is in this skill's folder, not in the
user's repository. The text must name one box, ticked or not, so a rerun never ticks a
neighbour. It keeps a backup of the body, sends the edit from memory, refuses a result
that is empty or differs anywhere but the boxes, refuses when the body changed since it was
read, and reads the body back. One gap stays open: GitHub has no conditional update, so an edit
someone makes in the moment between the script's last read and its write is overwritten, and
the read-back cannot show it. Where people edit an epic body by hand while agents tick it, agree
on one writer.
Never edit an issue body with `sed` and `gh issue edit`, however small the change. A
hand-written helper once blanked 11 issue bodies, and a body read with `gh -q .body` or
`gh api --jq .body` gains a line end on every round trip. `tests/tick.sh` in the kit's
repository exercises the script.

## Read before you do any of these

Squashing, force pushing, rebasing a stacked PR, resolving conflicts by script, auto-merge, a PR
that carries a migration or bumps a version a live worker checks. Each has a trap with a recorded
incident behind it: [references/git-traps.md](references/git-traps.md).
