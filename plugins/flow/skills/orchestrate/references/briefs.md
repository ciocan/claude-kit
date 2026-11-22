# Brief templates

Fill in the angle brackets. Sections marked optional can go. The agent definitions that ship with
this plugin (`implementer`, `reviewer`, `verifier`) already carry the standing rules, so a brief
sent to one of them can drop the lines marked (standing).

Four rules for every brief:

- Write it for a reader with no context. Never refer to "my memory" or "as discussed". Say "a
  benchmark note says" and quote the figure.
- Do not put your expected answer in a research or review brief. An agent handed a hypothesis
  returns it confirmed.
- File an issue before a brief or a doc cites its number. A document a brief tells the agent to
  read is on the base branch, or the brief gives the path of the copy to read.
- Every fact a brief states carries its source (a file and line, a command and its output) or the
  words "unverified, check it". Four briefs in two runs stated false facts, and one pointed to a
  brief file that had not been written yet.

## Implementer

```
You implement <issue ref> of <repo> (<stack>): <one sentence, the observable outcome>. It is slice
<k> of <n> of epic <epic ref>.

## Where you work
- Worktree <path>, branch <branch>, cut from <base ref> at <sha>. Work only there. Never write in
  <the user's checkout>. Use `git -C <path>`, never `cd` into another checkout.
- Scratch files only under <scratch dir>/<slug>/. Create it. Delete nothing outside it. (standing)
- Shared on this host, leave alone: <build caches>, <ports and servers you did not start>,
  <repo-wide formatters; format only the files you touched with <cmd>>.
- Never target production: <flags, keys, stores>. Production steps the slice needs go in your
  report as commands for me.
- Env: use <env file>. It holds no production credential. If you find that your env reaches
  production (a live key, a production queue or database), stop and say so. (standing)
- Shared with other agents and sessions: <backend by name>, lock <name>. You do not push to it, I
  do. [Or: you may push, in this order and as separate commands: `lock.py acquire <name>`,
  `claims.py check <name>`, <the subset check>, the push, `claims.py claim <name> <ref>`,
  `lock.py release <name>`. Go on only after exit 0. If the claims check exits with anything
  else, or the subset check or the push fails, run `lock.py release <name>`, then stop and
  report. If the push went through and `claims.py claim` fails, keep the lock, stop and report:
  code is deployed that no claim records. The lock is never broken for age, so one left behind
  blocks every later push until a person releases it.]
  Make your own test user and organisation with <command>. Never use <the shared test account>
  for a hand check.
- Before heavy runs check `free -g` and `uptime`. Wait while free memory is under <n> GB or load is
  over <n>. At most <one database container>.

## Read first
1. <issue command>. The spec. Each acceptance criterion needs a test or a named check.
2. <epic command>. Decisions already taken. Do not reopen them.
3. <AGENTS.md or CLAUDE.md and the docs it points to>.

## What the code does now (from an earlier read, verify it)   [optional]
<files, symbols, behaviour>. If the code differs, stop and report.

## Boundaries   [optional, for parallel slices]
- <other agent> on <branch> edits <files>. Keep your edits to <shared files> small and local.
- <later issue> will add <thing>. Shape <API> so it fits. Do not build it.

## Decisions taken and points left to you   [optional]
- <decision>
- <open point>. I expect <expectation>. Say what you chose and why.

## Gates
In the worktree, all must pass: <commands>. Write each gate's output to a file and read its exit
code. A test known to time out under load: run it once more alone and report both results.

## Hand check   [optional]
<a real run | a browser walk at <widths> in <themes> with a clean console | a measurement>. Paste
the output. Stop every server you start.

## Docs in the same change
<runbook>, <decisions log>.

## Commit and PR   [one line, chosen from the user's grant]
- Stage, write `.commit-msg.txt` (<convention>) and the PR body to <path>. Do not commit. I commit
  from your worktree.
- Commit (<convention>), push, open the PR with <command>. Never merge.

## Scope and stop conditions
Only <issue>. Out of scope: <list>. Stop and report instead of improvising when the code does not
match this brief, a criterion cannot be met as written, a gate fails after one honest retry, or
the task needs files outside the slice. (standing)

## Report back
As your final message, to the orchestrator: files changed with key line ranges; choices and why;
each acceptance criterion with its evidence or a plain statement that it does not hold; each
command with the tail of its real output; the hand check; what you skipped and why; what you
cleaned up; open doubts. (standing)
```

## Reviewer

```
Review <PR ref> of <repo> for correctness bugs: <one sentence on the change>. Round <n>.

## Where
<worktree>, branch <branch>, head <sha>. Your diff: `git -C <path> diff <base>...<head>`. Read
only: do not edit, stage or commit, do not move HEAD. Scratch under <scratch dir>/review-<n>/.
Throwaway tests are welcome if the tree ends as you found it. Containers and servers of your own
get your own names and ports and are removed when done.

## Spec
<issue command> (acceptance criteria), <epic command> (decisions), <PR view command> (the author's
account, unverified).

## What a bug costs here, worst first
<worst outcome>. Next: <...>. Cheap: <...>.

## Angles
Read the code and form your own view first. Then make sure you also covered these, which I have
not verified:
- <angle>
[Round 2. Job 1: each fix in <range> does what it says and broke nothing. Job 2: the whole change
with fresh eyes. Say where round 1 most likely missed something.]

## Rules
Do the review yourself, launch no subagents. Treat the PR body and any report as unverified
claims. Do not rerun the full suite. One focused command per named doubt.

## Report
As your final message. Findings ranked critical, important, minor. For each: file and line, what
is wrong, a concrete input or sequence that shows it, the smallest fix you would accept, and
whether you proved it (show the run) or read it. Then one line per area you checked and found
sound, so a clean area differs from an unvisited one. No style notes unless they hide a bug. If
nothing is above minor, say so plainly. I am deciding whether to merge.
```

## Adversarial verifier

```
You are the adversarial verifier of <PR ref | the uncommitted change in <worktree>> in <repo>
(<stack>). It implements <issue>: <one line>.

Assume the change is broken until proven otherwise. For each acceptance criterion look for a
concrete input or state where it fails. Report unverified claims, silently narrowed scope,
untested edge cases and regressions in adjacent code.

## Inputs
- Acceptance criteria: <issue command>. Decisions taken: <epic command>.
- The diff: <patch path | git command>.
- Project rules: <AGENTS.md or CLAUDE.md>.

## Rules
- Read-only on source. A mutation test copies the file aside, edits, runs, restores it byte for
  byte, then proves the tree unchanged.
- You may run tests, read-only calls against <dev environment>, and servers on a free port of your
  own. Never <the user's port or checkout>. Never production. Stop every server you start.
- <how browser checks and the smoke-test account work here>
- Env: <env file>, no production credential. If your env reaches production, stop and say so.
  (standing) [Read-only production requests allowed: at most <n> to <host>. Count them and stop at
  the cap.]
- Shared backend <name>: you do not push to it. If it changes under you, stop and give the time.
- Name one assumption your checks share with the implementer's tests (the same payment method,
  account type, fixture or locale) and break it.
- A finding is evidence: file and line, the input or state, what happens, what should happen, how
  you observed it (command and output, or "by reading, not run").

## Places I want attacked (not a complete list, find your own)
1. <trust boundary: who counts as authorised>
2. <a guard or test that can be bypassed>
3. <behaviour only a production build shows>
4. <what leaks to the wrong caller>
5. <limits and worst-case cost>

## Report
As your final message: (a) findings, most severe first, with severity (critical, important,
minor), evidence and a suggested direction; (b) per criterion: holds, fails or not verifiable,
with what you did; (c) what you checked and found fine; (d) proof the tree is unchanged.
```

## Researcher or explorer

```
Read-only <fact finding | comparison | audit | docs lookup> in <repo path> (<stack>). Change
nothing: no edits, commits, branch switches, installs, builds, containers, database or production
access. Thoroughness: <medium | very thorough>.

Why: I am deciding <X> and need <facts | a verdict> before <asking the user | writing an
implementation brief>. [Do not propose a design.]

## What ours does today   [optional]
<numbered facts the agent cannot cheaply rediscover>

## Where to look
<files and directories, in reading order>. For large files list the headings with
`grep -n '^## '` and open only what you need.

## Questions
1. <a question that names exact symbols, fields or commands>
[Finish with <obstacles ranked by size | a dependency-ordered list | a verdict per item>.]

## Rules
- Every claim carries a file:line you opened, the command and its output, or the doc page.
- Where the code has nothing, say "not found". Where you could not determine something, say so.
  Never guess. If only production data would settle a point, write the query instead of running it.
- Do the reading yourself. Launch no further agents.
- Scratch only under <scratch dir>/<slug>/.

## Report
As your final message, summary first: <one section per question | a table of <columns> | up to <n>
items, each with a verdict from <closed list>, a size and what you did not verify>.
```

## Briefs for cheaper models

A smaller model needs less judgement left open. Give exact commands with their flags, the sources
in reading order, the field names to look for, and a closed list of verdicts. Add "do not read
whole large files, grep and read ranges". Tell it to wait in the foreground: these agents tend to
end their turn while a background job is still running.
