---
name: smoke-test
description: Prove a change works by running the real thing. Drive the app in a browser while signed in, call the live stack, run the job on real data, and attach the evidence to the PR. Use before calling work done, before a merge, when briefing a verifier agent, and when the user says "smoke test it", "make sure it's smoke tested", "how was it verified?" or "is it smoke tested on the preview?".
---

# Smoke test

Tests prove the code. The smoke proves it runs. A green build and passing unit tests say nothing
about the page behind the login, the query against real data, or the deploy that just went out.
Done means verified and smoke tested, both.

## Who runs it

A verifier that did not write the change. See `fresh-eyes` for the brief. Functions where a miss
is expensive get several rounds.

## Web apps

1. Start your own server on a free port. Never stop or restart a dev server you did not start. It
   is the user's, and killing it costs them their session. Check first with `pgrep -fa "next dev"`
   or the stack's equivalent. Some frameworks refuse a second dev server in one checkout, so build
   and run the production server on another port.
2. On a remote dev box, use the host name the user reaches it by. `localhost` URLs in a report are
   useless to someone on another machine.
3. Sign in as the repository's smoke-test account (the runbook names it). Never script past a bot
   check on sign-up.
4. Walk every route the change touches, signed in. Check phone and desktop widths, light and dark
   themes, and the console for errors and hydration warnings.
5. Take screenshots, before and after for a visual change. Copy them out of the worktree before it
   is removed, because gitignored folders vanish with it.
6. If the browser tools cannot start for lack of a system Chrome, drive the repository's own
   Playwright Chromium from a small node script.

## End-to-end suites

Run only the specs that cover the changed code or screen, in full for the page you changed. Run
the whole suite only when a shared primitive, the layout, the proxy or a security header changed.
Say in the PR which specs ran, with counts, and that the full suite was left to CI.

## Services, APIs and data jobs

- Call the running service with real requests and compare against the data named in the issue.
- Run a pipeline change on a real slice. Compare counts before and after, and check the records
  the issue cites.
- After a deploy, smoke the deployed URL as well as the local build.
- Smoke at the scale that matters. A pipeline change is tried on a slice large enough to meet the
  rare shapes, with live data. Say how large the slice was.
- Finish the smoke of one item before starting the next.
- Fixtures for values that cross stores need full precision. A timestamp on a whole second hides
  a truncation between a microsecond store and a millisecond one.

## Evidence

The PR body says what rendered in the browser and what did not, the commands that ran with their
output, and holds the screenshots. When the environment could not check something, write that
down plainly. A number nobody could measure is not verified.

## Afterwards

Stop the server you started, by pid. Remove test databases, containers and stand-in endpoints,
and whatever the smoke itself created: test rows, uploaded files, generated output.
See `cleanup`.
