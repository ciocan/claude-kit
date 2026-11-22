# What a worktree does not separate

A worktree gives each agent its own files. Everything else is still shared: the database, the
hosted backend, the auth provider, the payment sandbox, the env file, the CI runners, the ports,
the memory. Two long runs recorded 22 and 14 collisions on such things.

Do this once, before the first launch, and again when a second session starts work in the same
repository.

1. List what the worktrees will share. The table below is the checklist.
2. Isolate what can be isolated: an instance per worktree, or per session.
3. Put a guard on the rest.
4. Write the result in the state note, so every brief can quote it.

## The table

| Shared thing | Isolate it | Guard when you cannot | What happened |
|---|---|---|---|
| Database or hosted backend deployment | A database per worktree, under its own name and port. A preview or per-branch deployment of a hosted backend | One lock. Only the orchestrator pushes. Before a push: the subset check, then the claims, then the push, each its own command | Sessions overwrote each other's deployed functions eight or more times. Verifiers ran on a backend that changed under them |
| Schema and migrations | The same instance as above | Land schema changes one at a time. Merge the integration branch before pushing | Rows written under one branch's schema made every other worktree's push fail. Three slices moved to new worktrees |
| Auth provider: users, organisations, rate limits | A dev instance per session, where the plan allows it | One test user and one organisation per agent, created by the agent and removed at the end. Never a shared one. No local sign-ins while a CI run with browser tests is in progress or about to start | Hand checks on a shared test organisation broke CI twice. 21 users created during two CI runs turned both red. A brief put the shared staff user into four agents' organisations |
| Third-party sandbox with account-wide settings (payments, mail, SMS) | A sandbox account per session | Lock, save the setting to a file, change it, restore it, read it back and compare. A watchdog restores it if the agent dies | Held seven times out of seven |
| Env files and the credentials in them | A dev-only env file per worktree, generated from a template, with no production credential | The brief names the env file. An agent that finds its env reaches production stops and says so. Read-only production checks get a request cap | A verifier ran its local server on a copied env file and reached production through it |
| Queues, caches and buckets a dev env can reach | Dev-only names or prefixes | Read the env for their addresses before the first run | The same incident |
| CI runners | Nothing to isolate | No two pushes within minutes. No measurement or load runs while a peer's pull request waits | Measurement runs stretched other sessions' CI to 20 to 31 minutes |
| Ports and dev servers | A port per worktree, taken from a number in the brief | Each agent starts its own server and stops it by pid | |
| Host memory, CPU and disk | A larger machine or fewer agents | Floors in the brief. The orchestrator holds launches above them | Load peaked at 53 with eleven agents. Tests failed on timing at load 40 |
| Build and package caches | A target directory per worktree, where that is cheap | Never clean a shared cache | See `traps.md` |
| A branch deployed to a shared environment | Nothing to isolate | Merges land one at a time. A skew check before each production deploy | The skew check ran four times and caught a real gap twice |
| Files every slice appends to (a decisions list, a changelog, an instruction file with a size cap) | One fragment file per slice | Land those pull requests one at a time | Each merge conflicted the next pull request |
| The repository itself: stash, refs, hooks, config | Nothing to isolate | Agents never `git stash`. A scratch branch holds work in progress | One agent found a stash entry it had not made |

## Guards that held

On a long run written rules were broken and scripts were not. A note said "times from the
machine" and its clock still ran 15 hours ahead. These held, most of them every time:

- **A lock** around each push to the shared backend.
- **The subset check**: every function deployed there must exist in my tree. It is its own
  command. Read what it prints, then push. Chained into one command, it listed a peer's two
  functions and the push removed them in the same breath.
- **The union push**: when a peer's unmerged branch is deployed, push both trees together or wait.
- **Save, change, restore, read back** for an account-wide setting, with a time box.
- **A kill switch**: unfinished work sits behind a flag that is off in production. A defect
  merged to the integration branch stayed out of production because of it.
- **A skew check** before every production deploy: is what runs there the same as the branch?

## Two scripts

They are in this skill's `scripts/` directory, in Python with the standard library only. Copy
them into the repository so they outlive the plugin version. `tests/shared-resources.sh` in the
kit's repository exercises both.

**`lock.py acquire|release|status <name>`** is a lock file opened with `O_EXCL`, so exactly one
caller wins. It is not built on `mkdir`: see the trap in `traps.md`. It records the owner label, the time and
a note. It never breaks a lock on its own, however old: it prints the owner
and the age and exits 1, and a person decides. Each session passes a label of its own with
`--owner` or `LOCK_OWNER`, because every command an agent runs is a new shell and a pid proves
nothing.

**`claims.py claim|release|list|check <resource>`** keeps one small file per claim in a folder
outside every repository. A claim says "this session deployed this ref to that shared
environment". `check` exits 1 when another session holds a claim there. A message from one
session to another can be refused by the permission system. This folder is the channel that still
works, so it is the written agreement between sessions.

A push to a shared backend, as separate commands:

```sh
lock.py acquire dev-backend --owner <label> --note "push for #<issue>" --wait 600
claims.py check dev-backend --owner <label>     # exit 1: someone else has code there
<the subset check>                              # read its output before the next line
<the push, or the union push>
claims.py claim dev-backend "<branch>@<sha>" "<what is deployed>" --owner <label>
lock.py release dev-backend --owner <label>
```

If the claims check exits 1, or the subset check or the push fails, release the lock before you
stop. `lock.py` never breaks a lock for age, so one left behind blocks every later push until a
person runs `release --force`.

Release the claim when the branch merges or its code is no longer deployed.

## The line for the state note

```text
Shared in this run (measured <time UTC>):
- <resource>: isolated per worktree as <how>
- <resource>: shared. Lock <name>. Pushed by <the orchestrator only | agents holding the lock>
- Env for agents: <file>, no production credential, checked with <command>
- Test accounts: one per agent, made with <command>, removed with <command>
- Production reads by verifiers: <not allowed | at most <n> requests to <host>>
```
