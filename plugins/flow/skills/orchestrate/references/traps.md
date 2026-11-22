# Traps

Each rule here comes from an incident. The guard is the command or the sentence that prevents it.
Git and merge traps are in the `ship-pr` skill.

## Briefing

- **Each agent gets its own scratch directory.** A shared scratchpad was emptied while six agents
  ran, taking the merge scripts and their logs. Brief sentence: "use only `<scratch>/<slug>/`,
  create it, delete nothing outside it". Keep your own long-lived scripts outside the scratchpad.
  A deleted script that is still running can be copied back from `/proc/<pid>/fd/255`.
- **Ask for the report as the final message.** The harness refuses report files written by
  subagents. A brief that asks for one costs a failed call.
- **Say who commits.** An agent under a no-commit rule refuses a relayed "commit it". Either the
  brief says "stage and write `.commit-msg.txt`, I commit from your worktree", or it grants the
  commit in so many words.
- **Check the issue is not already done.** An implementer spent about 100k tokens rediscovering a
  merged PR whose body had no closing reference.
- **Fetch before pointing an agent at "main".** A main checkout 36 commits behind sent research
  agents to read code that no longer existed.
- **Rerun the cheap gates after the agent's last edit.** "Full gate green" was true before its
  final change. Write "the agent reports" in the PR body for any gate you did not rerun.
- **Two agents, two message files.** Two agents sharing one `msg.txt` overwrote each other's
  commit message.

## Supervising

- **Keep the worktree until the PR is merged.** Resuming an agent with SendMessage needs it.
- **Use `git -C <path>`, never `cd`.** A `cd` that persisted put a commit in the user's checkout,
  and another time ran `worktree add` in the wrong repository.
- **Reviewers leave the tree as found.** A review left another branch checked out in an
  implementer's worktree.
- **Never run `git checkout -- .` or `git clean` in a worktree that may hold a fix round.** One
  did, and an uncommitted round was lost.
- **A file every PR appends to conflicts with every open PR.** After merging one, merge main into
  the open branches, and land such PRs one at a time.

## Shared backends and sandboxes

The checklist and the scripts are in [shared-resources.md](shared-resources.md).

- **The check and the push are two commands.** A check chained to a push listed a peer session's
  two functions and removed them in the same breath. That session's feature was broken on the dev
  backend for 28 minutes. Run the check, read it, then push.
- **A peer's unmerged branch on the shared backend means push the union or wait.** Pushing one
  tree removes what the other deployed. Two runs recorded eight or more such overwrites. Read the
  claims first (`claims.py check`).
- **Local sign-ins throttle CI.** An auth provider limits a dev instance as a whole. A verifier
  that created 21 users while two pull requests ran browser tests turned both red. Two local test
  batches in the 40 minutes before a push did it again.
- **A copied env file reaches production.** A verifier ran its local server on a copied env file
  and reached production through it. Agents get a dev-only env file.
- **One test user and one organisation per agent.** A brief told four agents to add the shared
  staff test user to their organisations. A CI spec failed and new sign-ins landed in another
  agent's organisation.

## Shell and processes

- **`pkill -f <text>` kills your own shell.** The shell's command line contains the text. Take the
  pid from `ps -eo pid,args | grep -E "[n]ame"` and `kill <pid>`.
- **A waiter that polls `pgrep -f <name>` never ends.** It matches itself and its siblings. 22 such
  shells outlived their task by three hours. Wait on a marker line in a log file.
- **`mkdir` is not a lock on every machine.** Where coreutils is the Rust rewrite (uutils 0.10),
  two `mkdir` calls on one path at the same moment both exited 0 in 22 of 300 tries, and a lock
  built on it let two writers in. Open the lock file with `O_EXCL`, as `lock.py` does. In a shell
  script, `set -C` before the redirect does the same.
- **Never read and write the same file in one expression.** A helper opened a file for writing
  before it read it and blanked the bodies of 11 issues for 47 minutes. A verifier noticed, and
  they came back from the tracker's edit history. Build the new content in a second file, check
  it, then move it. For issue checkboxes use `tick.py` in `ship-pr`.
- **A gate piped into `tail` hides its failure.** The pipe returns tail's exit code. Write the
  output to a file and branch on `$?`.
- **A backgrounded wait dies at the tool's time limit.** Long waits go in a script started with
  `setsid nohup`, which writes a marker line when done.
- **Processes started by the session do not survive it.** After a restart, start the merge queue
  and the monitors again from the commands in the state note.

## The host

- **Agents share the machine with CI and with the user.** Three implementers with containers, a
  reviewer loading a large graph and two CI runs filled memory and swap, and the kernel killed
  another session's process. Put the limits in the brief: check `free -g` and `uptime` first, wait
  under a floor, one database container each, no load tests on the dev box.
- **Do not push two branches within minutes of each other** while agents are testing. Each push is
  a full CI run on the same host.
- **Never clean a shared build cache.** The CI runner and the other agents build from it.
- **A build over the whole workspace in every worktree fills the disk.** One run produced a
  191 GiB target directory. Build and test the package that changed.
- **On many hosts `/tmp` is RAM.** No build directories there.
- **After a failed CI run, remove the containers it left.**

## Usage limits

- **Seven agents at once hit the five-hour limit and all died mid-task.** Keep a wave to three
  implementers plus one or two reviewers, and check usage between waves.
- **After a reset, resume with SendMessage.** The agent keeps its context. Respawning loses it.
- **An agent killed by one model's weekly limit cannot be resumed on another model.** Send a fresh
  agent pointed at the branch, the worktree and the last report.
- **Never switch models on your own when a launch fails on a limit.** Report it and wait.

## Data and secrets

- **Never print real personal data or customer identifiers in tool output.** Strip sample fields
  before printing (`jq 'del(.samples)'`), and select counts, not rows.
- **No real person's name or number in tests, seeds, docs or commits.** A pushed commit stays
  reachable through the PR ref after a force push.
- **Never pass a secret as a command argument.** Process lists and telemetry record arguments. Pipe
  it on stdin.
- **Some secret tools write the value to stderr too.** Never merge stderr into captured output
  when reading a secret.

## Production

- **Migrations run before the code that needs them.** A deploy that expected a missing column
  failed about 360,000 records. Never rename a migration that any environment has applied.
- **One user of a deploy checkout at a time.** A merge chain switched the tree under a running
  migration. Check for running chains (`pgrep -fa '[m]igrate-'`, `tmux ls`) before starting one.
- **Do not merge while a run that the deploy would restart is in progress.** Queue the green PRs.
- **Apply an alert on absent data only after the job it watches is deployed.** One paged for
  twelve hours.
- **A permission refusal is final for you.** Hand the exact line to the user once. Do not retry it
  in another form. See `owner-scripts`.
