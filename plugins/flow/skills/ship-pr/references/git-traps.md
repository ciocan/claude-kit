# Git and merge traps

Each entry gives what happened, why, and the guard.

## Cleanup chained on the wrong verdict

A PR watcher exited 0 on a failed CI run. The cleanup, chained with `;`, deleted the branch, and
GitHub closed the PR. A second time an issue was closed while its PR was still open.

- The watcher's exit code means it stopped watching.
- `;` runs the next command after a failure. `&&` does not.
- A "mergeable: UNKNOWN" answer is GitHub recomputing for about a minute after another merge.
  Retry, do not treat it as a verdict.

Guard: start the cleanup with the `MERGED` test and join every later step with `&&`, the issue
close and its comment included.

Recovery when a branch was deleted under an open PR:

```sh
git fetch origin refs/pull/<n>/head:<branch> && git push origin <branch> && gh pr reopen <n>
```

## Squash by soft reset on a stale branch

`git reset --soft origin/main && git commit` on a branch that does not contain `origin/main`
writes the branch's old tree. Everything merged since the branch was cut is silently reverted, and
a "tree equals branch head" check still passes. One such squash reverted nine files of another PR.

Guard:

```sh
git merge-base --is-ancestor origin/main HEAD || git rebase origin/main
git diff --name-only origin/main HEAD    # must equal the files you meant to change
```

## Auto-merge without required checks

In a repository with no required checks, `gh pr merge --auto` merges at once, before CI has run on
the head. Watch the checks, then merge by hand:

```sh
gh pr checks <n> --watch && gh pr merge <n> --squash
```

## A merge call that merges nothing

`gh pr merge` on a pull request that is `CONFLICTING` can return without merging and without a
clear error. Read `mergeable` before the call and the `MERGED` state after it. The merge train
script in `long-haul` does both.

## Stacked PR after its base merged

A force push that lands while the base branch is being deleted gets no CI run, and retargeting
with `gh pr edit --base` fires an event the workflow ignores. Retarget first, push second, then
confirm a run exists:

```sh
gh run list --branch <head> --limit 3
gh pr close <n> && gh pr reopen <n>     # only when no run started
```

Deleting the integration branch (the "Delete branch" button after a release PR) makes GitHub
retarget every open PR based on it to the default branch. Restoring the branch does not move them
back.

## Conflict markers pushed

A merge whose output was read through `tail` hid a conflicted Markdown file, and the build and the
linters passed with the markers in it. Before committing any merge:

```sh
git status --short | grep -E '^(UU|AA|DU|UD)'
git grep -n -E '^(<<<<<<<|=======|>>>>>>>)( |$)'     # must print nothing
```

## Conflicts resolved by script

An unanchored `sed` over a long, often-edited file rewrote 120 lines, and replacing a whole hunk
dropped two bullets. Address lines by number (`sed -i '<N>s/…/…/'`), replace only the conflicting
lines, and compare the list of headings or bullet keys with the file before the merge.

## Force push and branch delete

Permission classifiers refuse `git push --force` and remote branch deletes even under a merge
grant. Do not plan on them. To drop commits from a pushed branch, push the tree as a new branch
and leave the old one to the user:

```sh
git switch -c <new> && git reset --soft <base> && git commit && git push -u origin <new>
```

Commits that reached a PR stay reachable through `refs/pull/<n>/head` after a force push. Treat
anything pushed as published.

## Release PRs

Merge the integration branch into the production branch with a merge commit. A squash leaves the
two branches without shared ancestry, and the next release PR conflicts on every file the first
one touched. The repair is a back-merge of the production branch into the integration branch.

## Rebases that duplicate

A "keep both sides" rebase can leave the same logic twice, once from each side, and still
compile. Diff the rebased head against the base and read it. Refuse to push when a script the
rebase touched fails `bash -n`.

## PRs that carry a migration

The code deploys on merge and the migration is a separate step. If the code lands first, it runs
against the old schema. Apply the migration first, or hold the PR until the person who applies it
is there. Never rename a migration that any environment has applied. Write `IF NOT EXISTS`.

## PRs that bump a version a live worker checks

A worker that refuses entries whose version differs from the last build stops the moment the bump
merges. Keep the PR open until the full rebuild can start the minute it lands.

## Merges during a long run

A merge that redeploys a service restarts whatever that service was running. Check for running
jobs before merging, and queue green PRs until they finish.

## The wrong repository

After a `cd` inside a compound command, later git commands ran in another repository. Name the
repository in every command: `git -C <repo> …`, and run `git -C <worktree> log -1` on a new
worktree before handing it to an agent.

## Bot footers

Squash merges copy the PR body into the commit. Strip tool footers from the body before the merge
if the repository does not want them in history.
