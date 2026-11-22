# What stalls a long run

Taken from nine goals that ran between half a day and nine days, and two later runs. The cost
column is what the records show. Almost none of these are bugs in the product being built.

## Waiting for the user

| What happened | Cost seen | Guard |
|---|---|---|
| A step the session may not run sat until the user came back | 6 h, 10.5 h, 1.5 days | Ask what blocks before they leave. Keep a numbered paste file. Send a push notification the moment a paste becomes the only blocker |
| A paste was typed wrong (a space after `!`) and the next step queued behind it | 80 min, then 54 min | One line per step, absolute paths, no space after `!`, the expected last line stated |
| The script handed to the user failed on its first real run, after waiting all night | 10.5 h | Give every owner script a dry run that exercises the same commands, and run that dry run yourself before handing it over |
| The goal as worded could not be reached | 6 days before it was re-worded | Measure early. Say "not reachable as worded" with numbers and propose the new wording |

## The session stopped by itself

| What happened | Cost seen | Guard |
|---|---|---|
| The session went idle with jobs pending and nothing armed | 4.5 h | Never end a turn without a watcher or a wake-up for each pending job |
| A watcher matched its own command line and never fired | 3 h, 18 min, and a third time | Watch a marker line in a log. Never `pgrep -f` |
| A wait in a background shell was killed at the tool's time limit | found after a compaction | Long waits run as detached scripts |
| A usage limit killed every agent | 3 h, 5 h | Check usage before each wave. Resume with SendMessage after the reset. A fresh agent if the model changed |
| A restart left two sessions driving one goal | an evening | One session owns the goal. The other finishes its agents and stops |

## Authority and the note

From two later runs of 64 and 20 hours. Written rules were broken there. Scripts and checks held.

| What happened | Cost seen | Guard |
|---|---|---|
| Only the user's steps remained and the goal check fired every turn | 19 prompts in one night, dozens in another run | Word the goal to end where your part ends. One line, a long wake-up, no action |
| A goal check was taken as leave to lift a hold | A merge the session had called the user's went in, with a defect that took 4 hours to find and fix | A hold told to the user is theirs to lift. The harness asking is not the user answering |
| A general yes was read as covering a step the session had called the user's | A production step ran before the grant that named it | A yes that names the step. The grant note is written before the action |
| Times in the note were typed from memory | Up to 15 hours off, backwards three times, closures logged up to 14 hours off | `note.sh add` stamps from the machine |
| The log was never rotated | 4,913 lines, 393 KB | `note.sh` warns at 300 lines and rotates |
| A message to a peer session was refused | The sessions overwrote each other's deployed code 8 or more times | The claims folder, `claims.sh` |
| A claim about deployed state was repeated without measuring | A wrong status for hours | Re-measure, and give the time of the measurement |

## Long jobs

| What happened | Cost seen | Guard |
|---|---|---|
| A job ran on a stale build of the workers and its result was discarded | one run, then 1 h | Check the build the workers run before a start. Wait for old builds to age out |
| A long pass failed late and lost its progress | about a day | Checkpoints. A progress line every hour. Confirm the data is fresh before auditing it |
| The ETA was read from a counter that counted something else | the end moved 7 h | Write down what the counter counts. Compute the ETA from the measured rate |
| A check expected to take an hour ran almost nine, filled the disk and took the database down | an evening | A time box and a disk floor on every long job. Stop at a multiple of the expected time and report |
| A vendor suspended an account mid-run | 1.7 h, every job halted | Jobs halt in a state they can resume from. No switch to a paid alternative without the user |

## Merges and CI

| What happened | Cost seen | Guard |
|---|---|---|
| A merge redeployed a service during its nightly run | a three-night gate reopened | Merge windows in the note's top block, with CI time counted |
| A PR merged before the build it depended on could run | 10.5 h | Hold such a PR until its follow-up can start at once |
| A CI run sat queued with no job | 85 min | After a push confirm a run started. Re-trigger when none did |
| Cleanup ran after a watcher's exit code, not after a merged state | minutes, three times | The `MERGED` guard in `ship-pr` |
| A squash on a stale branch reverted the main branch | 1 h | The ancestor check in `ship-pr` |

## The machine and the neighbours

| What happened | Cost seen | Guard |
|---|---|---|
| Memory pressure from another project killed a chain's driver | minutes, and a watcher that was not restarted | Floors before every start. After any kill, re-check every watcher |
| Another session cleaned a shared build cache | one CI failure | Shared caches are left alone |
| A peer's merge moved the main branch under a script written for the user | a rerun | Agree windows with peers in writing. Re-check the commit before each paste |
| A note said "no further merges are planned" and was a day old | corrected in time | Ask the peer or measure again before relying on a note older than a day |
