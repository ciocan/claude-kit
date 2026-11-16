---
name: cleanup
description: Leave the machine as you found it after a run. Stop the servers and jobs you started, remove merged worktrees and branches, delete containers, sandboxes, caches and rented instances, and report disk before and after. Use at the end of an eval chain, benchmark, dev-server or agent session, and when the user says "cleanup", "clean up all unused worktrees", "stop all servers", "free up disk space", "what disk space can be cleared?" or asks why a directory is so large.
---

# Cleanup

Clear what you started without being asked, and say in the recap what was cleared. Never leave it
for the user.

## End of a run

- Servers you started, killed by pid. A dev server you did not start is the user's.
- Background shells, waiters, monitors and scheduled loops.
- Test databases and containers, including the ones a failed CI run left behind.
- Sandbox VMs and the directories they leave on disk. Killing the process does not remove the
  disk image.
- Rented GPU or cloud instances. They cost money while idle. Confirm the count is zero.
- Temporary config overrides and large run dumps outside the repository, once their figures are
  recorded somewhere durable.

## Worktrees and branches

Remove them only after the PR's state reads `MERGED`, and join every step with `&&`:

```sh
[ "$(gh pr view <n> --json state -q .state)" = MERGED ] \
  && git -C <repo> worktree remove <path> \
  && git -C <repo> branch -d <branch>
```

A watcher's exit code means it stopped watching, not that the PR merged. Copy gitignored
artefacts (screenshots, reports) out of the worktree first. List unmerged worktrees for the user
and leave them alone.

## Freeing disk

1. `df -h /` before.
2. Find the weight: `du -xh --max-depth=2 <dir> 2>/dev/null | sort -rh | head -20`.
3. Usual candidates: container images and build cache (`docker system df`), package caches (npm,
   pnpm, bun, uv, go build, cargo `target`), build directories inside stale worktrees, old logs.
4. Never touch data volumes, databases, or anything a process of the user or another session
   holds open. Ask first.
5. `df -h /` after, and report what each step freed.

## Traps

- `pkill -f <text>` run from the session kills the session's own shell, whose command line holds
  the text. Kill by pid, or bracket one letter of the pattern: `pgrep -f "[n]ext dev"`.
- A waiter that loops on `pgrep -f <name>` matches itself and never ends. Wait on a marker line in
  a log.
- On many hosts `/tmp` is RAM. Never put a build directory there.
- A build over a whole workspace inside each worktree multiplies the disk. Build the package you
  changed, or share one target directory and delete it afterwards.

## Recurring

When the user wants this on a timer, set it up with `/loop` and tell them how to stop it.
