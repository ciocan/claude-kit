#!/usr/bin/env python3
"""Count what happened in one Claude Code session transcript, and optionally write a digest.

Usage:
  transcript-digest.py <session.jsonl> [--out digest.md] [--json | --user-messages]
                       [--dedupe-seconds N] [--report-chars N] [--quiet]

The transcript is the main session file, ~/.claude/projects/<path slug>/<session id>.jsonl. Agent
transcripts live beside it in <session id>/subagents/agent-<id>.jsonl and are not read here.

Output:
  (default)         the counts as text on stdout
  --json            the same counts as one JSON object on stdout
  --user-messages   every message counted as the user's, one per line:
                    <timestamp> TAB <typed|queued> TAB <first 200 characters, newlines as spaces>
  --out FILE        also write a chronological digest for an evidence agent to read

What each count means:
  span                 first and last timestamp found in the transcript.
  compactions          system records with subtype compact_boundary, each with its timestamp, the
                       token count before it (compactMetadata.preTokens) and its trigger.
  compaction summaries user records flagged isCompactSummary (the summary pasted after a compaction).
  user messages        what the user sent: typed at the prompt, or queued while the session was
                       busy. Slash commands and ! shell commands count, and are also counted apart.
                       Harness lines are not the user's (see HARNESS_PATTERNS and system lines).
  duplicates merged    sightings of a queued message that were folded into one message.
  late merges          of those, deliveries that came after the window but matched a message
                       still waiting in the queue.
  withdrawn            queued messages the user pulled back out of the queue (popAll) before they
                       were delivered. They are not the user's messages and are not listed.
  system lines         user-role records the harness wrote, by kind. queued system lines are the
                       same for queue records, including harness text that passed through the
                       queue on its way to a system record.
  interrupts           "[Request interrupted by user ..." markers.
  questions to user    AskUserQuestion tool calls.
  launches             Agent (or the older Task) tool calls, by subagent_type and model. A launch
                       with no subagent_type is "(default)"; with no model, "(inherit)".
  agent messages sent  SendMessage tool calls, that is messages to a running agent.
  tool errors          tool results with is_error set. This includes denials.
  permission denials   tool results whose user record carries toolDenialKind, by that kind. When
                       the field is missing, the two fixed refusal texts of the harness count.
  stop-hook prompts    user records starting "Stop hook feedback:", where a Stop hook refused
                       the stop and fed its reason back.
  goal checks          user records starting "Goal check-in:" (goal check feedback), and
                       notifications whose queueOrigin.source is goal-checkin.
  assistant turns      distinct assistant message ids with usage. One reply is written as several
                       records that repeat the same usage, so records are not turns.
  context              input + cache read + cache creation tokens per turn: median and max.
  unparsed lines       lines that are not a JSON object. They are skipped.
  malformed records    JSON objects with a field of an unexpected type (a message that is a
                       string, a text that is null, a token count that is a string). They are
                       skipped whole, so no count takes half of one.

Two lessons this script exists for:
  1. A message the user types while the session is busy is not stored as a plain user record. It
     is a queue-operation record (enqueue), and then either a queued_command attachment when it is
     absorbed mid-turn, or a user record with promptSource "queued" when it is dequeued later. A
     first digest that read only user records missed 13 of 25 of the user's messages, among them
     every authorisation given that night. This script reads all three and counts a
     message once. The user can also pull queued text back (popAll). Such a message was never
     sent, so it is not counted, and the digest says it was withdrawn.
  2. Timestamps come from the transcript, never from the session's own notes.

Deduplication: one message is at most one enqueue, one queued_command attachment and one user
record carrying the same normalised text (stripped, whitespace collapsed; a ! shell command is
keyed by the bare command) within --dedupe-seconds of each other (default 300). A user record
that comes out of the queue also merges with an earlier enqueue of the same text that is still
waiting in the queue, however long ago it was queued. A user record typed at an idle prompt
(promptSource "typed") is never merged, so a user who sends the same words twice is counted
twice. --dedupe-seconds 0 turns all merging off, and with it the move of harness text out of the
user's messages; withdrawals still apply.

Exit codes: 0 done, 2 the transcript cannot be read.
"""
import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import datetime

# Harness lines, matched against the start of the text (after leading whitespace). Records that
# carry metadata (isMeta, a non-human origin, promptSource "system") are classified by that first.
# These patterns cover records without such metadata, and queue records, which never carry it.
# Anything that matches nothing counts as the user's: a system line counted as the user's is
# visible in --user-messages, a user message dropped as a system line is not.
HARNESS_PATTERNS = [
    # A background task or agent finished. Carries the agent's result.
    ('task-notification', r'<task-notification'),
    # A reminder the harness attaches to a turn.
    ('system-reminder', r'<system-reminder'),
    # Output of a local slash command, and the caveat written before it.
    ('local-command-output', r'<local-command-(?:stdout|stderr|caveat)'),
    # Output of a shell command the user ran with "!". The command itself is the user's.
    ('shell-output', r'<bash-(?:stdout|stderr)'),
    # A running agent writing to the session, delivered through the queue.
    ('agent-message', r'<agent-message'),
    # A message from another session, delivered through the queue.
    ('cross-session-message', r'<cross-session-message'),
    # Written when the user pressed Esc, with or without "for tool use".
    ('interrupt', r'\[Request interrupted by user'),
    # A Stop hook refused the stop and its reason was fed back as a prompt.
    ('stop-hook', r'Stop hook feedback:'),
    # A session-scoped Stop hook was installed (by a goal, for example).
    ('stop-hook', r'A session-scoped Stop hook is now'),
    # Goal check feedback: the goal condition was evaluated and the result fed back.
    ('goal-check', r'Goal check-in:'),
    # A peer session wrote to this one.
    ('peer-session', r'Another Claude session sent a message'),
    # The body of a skill loaded by the Skill tool.
    ('skill-body', r'Base directory for this skill:'),
    # The summary pasted after a compaction, when isCompactSummary is missing.
    ('compaction-summary', r'This session is being continued from a previous conversation'),
    # Queued by the harness after the user stopped agents: "2 background agents were stopped by
    # the user: ...". It reads like the user's words and is not.
    ('agents-stopped', r'\d+ background agents? (?:was|were) stopped by the user'),
    # The same notice for one agent: 'Background agent "<name>" was stopped by the user.'
    ('agents-stopped', r'Background agent .{0,300}? was stopped by the user'),
    # The prompt a running /loop feeds the session on each tick. It passes through the queue.
    ('loop', r'# Autonomous loop tick'),
    # The prompt a /loop feeds when it checks whether to continue.
    ('loop', r'# Autonomous loop check'),
    # Queued by the harness when the plan's usage limit resets, to resume the work.
    ('usage-limit-reset', r'Your claude\.ai usage limit has reset'),
    # Written after the user stopped a response from a remote surface.
    ('response-stopped', r'Your response above was stopped by'),
    # A check-in the session scheduled for itself fired.
    ('scheduled', r'Scheduled check-in set by this session'),
]
_COMPILED = [(kind, re.compile(r'\s*' + rx, re.S)) for kind, rx in HARNESS_PATTERNS]

# The two refusal texts the harness writes into a tool result when toolDenialKind is absent.
DENIAL_TEXTS = [
    ('user-rejected', re.compile(r"The user doesn't want to proceed with this tool use")),
    ('permission-denied', re.compile(r'Permission to use \S+ (?:has been|was) denied')),
]

LAUNCH_TOOLS = ('Agent', 'Task')
TOKEN_FIELDS = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')
PROGRESS_MIN_BYTES = 20 * 1024 * 1024


class Malformed(Exception):
    """A JSON record with a field of a type the script does not expect."""


def harness_kind(text):
    for kind, rx in _COMPILED:
        if rx.match(text):
            return kind
    return None


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(p.get('text') or '' for p in content
                        if isinstance(p, dict) and p.get('type') == 'text')
    return ''


def said(content):
    """The text of a message, or [image] for a message that holds only images."""
    txt = text_of(content).strip()
    if not txt and isinstance(content, list) and any(
            isinstance(p, dict) and p.get('type') == 'image' for p in content):
        return '[image]'
    return txt


def norm(text):
    return ' '.join(text.split())


def seconds(ts):
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError):
        return None


def origin_kind(rec):
    o = rec.get('origin')
    return o.get('kind') if isinstance(o, dict) else o


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_shape(o):
    """Raise Malformed when a field the script reads has a type it does not expect."""
    def want(ok, what):
        if not ok:
            raise Malformed(what)

    def parts(content, where):
        want(content is None or isinstance(content, (str, list)), where + ' content')
        for p in content if isinstance(content, list) else ():
            want(isinstance(p, dict), where + ' part')
            want(p.get('text') is None and 'text' not in p or isinstance(p.get('text'), str), where + ' text')
            want(isinstance(p.get('input', {}), dict), where + ' input')
            want(p.get('content') is None or isinstance(p.get('content'), (str, list)), where + ' result')

    want(o.get('timestamp') is None or isinstance(o.get('timestamp'), str), 'timestamp')
    want(o.get('origin') is None or isinstance(o.get('origin'), (dict, str)), 'origin')
    want(o.get('queueOrigin') is None or isinstance(o.get('queueOrigin'), dict), 'queueOrigin')
    if 'compactMetadata' in o:
        meta = o['compactMetadata']
        want(isinstance(meta, dict), 'compactMetadata')
        want(meta.get('preTokens') is None or is_int(meta.get('preTokens')), 'preTokens')
    if 'message' in o:
        msg = o['message']
        want(isinstance(msg, dict), 'message')
        parts(msg.get('content'), 'message')
        usage = msg.get('usage')
        want(usage is None or isinstance(usage, dict), 'usage')
        for f in TOKEN_FIELDS if usage else ():
            want(usage.get(f) is None or is_int(usage.get(f)), f)
    if 'attachment' in o:
        a = o['attachment']
        want(isinstance(a, dict), 'attachment')
        parts(a.get('prompt'), 'attachment')
        want(a.get('origin') is None or isinstance(a.get('origin'), (dict, str)), 'attachment origin')
    if o.get('type') == 'queue-operation':
        parts(o.get('content'), 'queue')


def user_command(text):
    """Turn a slash command or a ! shell command record into what the user typed, else None."""
    s = text.lstrip()
    if s.startswith('<command-') and '<command-name>' in s:
        name = re.search(r'<command-name>(.*?)</command-name>', s, re.S)
        args = re.search(r'<command-args>(.*?)</command-args>', s, re.S)
        cmd = (name.group(1).strip() if name else '').lstrip('/')
        return 'slash', ('/' + cmd + (' ' + args.group(1).strip() if args and args.group(1).strip() else ''))
    if s.startswith('<bash-input>'):
        m = re.search(r'<bash-input>(.*?)</bash-input>', s, re.S)
        return 'shell', '!' + (m.group(1).strip() if m else '')
    # A slash command can also arrive as plain text, through the queue for example.
    if re.match(r'/[A-Za-z][\w:.-]*(?:\s|$)', s):
        return 'slash', s
    return None


def merge_key(text, command):
    """What two sightings of one message share. A shell command is queued as the bare command
    and delivered wrapped in <bash-input>, so it is keyed without its bang."""
    if command and command[0] == 'shell':
        return norm(command[1][1:])
    return norm(text)


class Digest:
    """The --out lines, kept in memory so a line can be corrected when a later record shows
    that a queued message was withdrawn or was harness text."""

    def __init__(self, on):
        self.lines = [] if on else None

    def emit(self, line):
        if self.lines is None:
            return None
        self.lines.append(line)
        return len(self.lines) - 1

    def replace(self, idx, line):
        if self.lines is not None and idx is not None:
            self.lines[idx] = line

    def write(self, path):
        with open(path, 'w', encoding='utf-8') as fh:
            for line in self.lines:
                fh.write(line + '\n')


class Messages:
    """The user's messages, with the queue's repeated sightings of one message merged."""

    def __init__(self, window):
        self.window = window
        self.items = []
        self.by_key = collections.defaultdict(list)
        self.merged = 0
        self.late = 0

    def live(self):
        return [m for m in self.items if m['state'] == 'live']

    def add(self, ts, text, source, queued, mergeable, command=None, raw=None):
        """Record one sighting. Returns (message, is_new)."""
        key, sec = merge_key(text, command), seconds(ts)
        if self.window > 0 and mergeable and sec is not None:
            cands = [m for m in self.by_key.get(key, ())
                     if m['state'] == 'live' and m['mergeable'] and source not in m['sources']]
            near = [m for m in cands if any(abs(sec - s) <= self.window for s in m['secs'])]
            if near:
                return self._merge(near[-1], sec, source, queued, text, command), False
            # A queued message waits until the session is free, which can be long after the
            # window. While it is still in the queue, its delivery is the same message.
            waiting = [m for m in cands if source == 'user' and self._waiting(m) and m['secs'][0] <= sec]
            if waiting:
                self.late += 1
                return self._merge(waiting[0], sec, source, queued, text, command), False
        m = {'ts': ts or '', 'text': text, 'key': key, 'raw': raw if raw is not None else text,
             'sources': {source}, 'secs': [sec] if sec is not None else [], 'queued': queued,
             'mergeable': mergeable, 'command': command, 'state': 'live', 'delivered': False,
             'line': None}
        self.items.append(m)
        self.by_key[key].append(m)
        return m, True

    def _merge(self, m, sec, source, queued, text, command):
        m['sources'].add(source)
        m['secs'].append(sec)
        m['queued'] = m['queued'] or queued
        if command and not m['command']:
            m['command'], m['text'] = command, text
        self.merged += 1
        return m

    @staticmethod
    def _waiting(m):
        return m['state'] == 'live' and m['sources'] == {'enqueue'} and not m['delivered'] and m['secs']

    def delivered(self, text):
        """A remove record names a queued text that was handed to the session."""
        for m in self.by_key.get(norm(text), ()):
            if self._waiting(m):
                m['delivered'] = True
                return

    def withdraw(self, content, ts):
        """popAll puts every waiting message back into the prompt, joined by newlines."""
        sec = seconds(ts)
        joined = '\n' + content + '\n'
        flat = norm(content)
        out = []
        for m in self.items:
            if not self._waiting(m) or (sec is not None and m['secs'][0] > sec):
                continue
            raw = m['raw'].strip('\n')
            if ('\n' + raw + '\n') in joined or m['key'] == flat:
                m['state'] = 'withdrawn'
                out.append(m)
        return out

    def take_back(self, key, sec):
        """A queued sighting turned out to be harness text: remove it from the user's messages."""
        if self.window <= 0 or sec is None:
            return None
        for m in reversed(self.by_key.get(key, ())):
            if (m['state'] == 'live' and m['sources'] <= {'enqueue', 'attachment'}
                    and any(abs(sec - s) <= self.window for s in m['secs'])):
                m['state'] = 'moved'
                return m
        return None


class Progress:
    """Plain progress on stderr for big files: a start line, then a line every few seconds."""

    def __init__(self, path, quiet):
        self.total = os.path.getsize(path)
        self.on = not quiet and self.total >= PROGRESS_MIN_BYTES
        self.tty = sys.stderr.isatty()
        self.start = self.last = time.time()
        if self.on:
            print(f'transcript-digest: reading {os.path.basename(path)}, '
                  f'{self.total / 1e6:.0f} MB, from the start', file=sys.stderr, flush=True)

    def tick(self, done, records, users):
        if not self.on:
            return
        now = time.time()
        if now - self.last < (0.5 if self.tty else 5):
            return
        self.last = now
        frac = done / self.total if self.total else 1
        eta = (now - self.start) * (1 - frac) / frac if frac else 0
        line = (f'transcript-digest: {done / 1e6:.0f}/{self.total / 1e6:.0f} MB {frac:.0%}, '
                f'eta {eta:.0f}s, records {records}, user messages {users}')
        if self.tty:
            print('\r' + line, end='', file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)

    def done(self):
        if self.on and self.tty:
            print(file=sys.stderr, flush=True)


def scan(args, dg):
    c = {
        'first': None, 'last': None, 'records': 0, 'unparsed': 0, 'malformed': 0, 'sidechain': 0,
        'compactions': [], 'compaction_summaries': 0,
        'system_lines': collections.Counter(), 'queued_system_lines': collections.Counter(),
        'interrupts': 0, 'asked': 0, 'launches': collections.Counter(), 'sent': 0,
        'tool_errors': 0, 'denials': collections.Counter(), 'stop_hook': 0,
        'goal_feedback': 0, 'goal_notifications': 0, 'turns': {}, 'output_tokens': 0,
    }
    msgs = Messages(args.dedupe_seconds)
    # Texts the harness marked as its own, by hash, so a queued copy of one is not the user's.
    harness_seen = collections.defaultdict(list)
    emitted = set()
    prog = Progress(args.transcript, args.quiet)
    done = 0

    def user_line(m):
        label = 'queued while busy' if m['queued'] else 'typed'
        return f"\n### [{m['ts'][5:16]}] USER ({label}): {m['text'][:3000]}"

    def user_msg(ts, text, source, queued, mergeable, command=None, raw=None):
        m, new = msgs.add(ts, text, source, queued, mergeable, command, raw)
        if new:
            m['line'] = dg.emit(user_line(m))
        else:
            dg.replace(m['line'], user_line(m))

    def system_line(ts, kind, text, counter):
        counter[kind] += 1
        if counter is c['system_lines']:
            if kind == 'interrupt':
                c['interrupts'] += 1
            elif kind == 'stop-hook' and text.lstrip().startswith('Stop hook feedback:'):
                c['stop_hook'] += 1
            elif kind == 'goal-check':
                c['goal_feedback'] += 1
        # A notification or agent message is written to the queue and again as a user record.
        # The digest shows it once.
        if kind in ('task-notification', 'agent-message', 'peer-session'):
            key = hash(norm(text))
            if key in emitted:
                return
            emitted.add(key)
        if kind in ('agent-message', 'peer-session') or (kind == 'task-notification' and '<result>' in text):
            dg.emit(f'\n[{ts[5:16]}] AGENT REPORT: {text[:args.report_chars]}')
        elif kind == 'task-notification':
            # Most notifications say a shell or agent finished. Keep only the ones that did not.
            st = re.search(r'<status>(failed|killed|stopped)</status>', text)
            if st:
                dg.emit(f'[{ts[5:16]}] SYSTEM task {st.group(1)}: {" ".join(text.split())[:300]}')
        else:
            dg.emit(f'[{ts[5:16]}] SYSTEM {kind}: {" ".join(text.split())[:300]}')

    def harness_kind_seen(txt, ts):
        """The kind of a harness record with this text near this time, if one was seen."""
        sec = seconds(ts)
        if msgs.window <= 0 or sec is None:
            return None
        for s, kind in harness_seen.get(hash(norm(txt)), ()):
            if abs(sec - s) <= msgs.window:
                return kind
        return None

    def queued_sighting(ts, txt, source, raw):
        """An enqueue or a queued_command attachment: harness text or the user's."""
        kind = harness_kind(txt) or harness_kind_seen(txt, ts)
        if kind:
            if source == 'enqueue':
                system_line(ts, kind, txt, c['queued_system_lines'])
            return
        # A queued shell command is stored as the bare command, so a queued text that starts
        # with "!" is an ordinary message that happens to start with a bang.
        user_msg(ts, txt, source, True, True, user_command(txt), raw)

    def harness_user_record(ts, kind, txt):
        """A user record the harness marked as its own. A queued copy of it seen earlier was
        counted as the user's; move it to the queued system lines."""
        system_line(ts, kind, txt, c['system_lines'])
        sec = seconds(ts)
        if sec is None:
            return
        harness_seen[hash(norm(txt))].append((sec, kind))
        m = msgs.take_back(norm(txt), sec)
        if m:
            c['queued_system_lines'][kind] += 1
            dg.replace(m['line'], f"[{m['ts'][5:16]}] SYSTEM {kind} (queued): {' '.join(txt.split())[:300]}")

    def record(o):
        if o.get('isSidechain'):
            c['sidechain'] += 1
            return
        ts = o.get('timestamp') or ''
        if ts:
            c['first'] = min(c['first'], ts) if c['first'] else ts
            c['last'] = max(c['last'], ts) if c['last'] else ts
        t = ts[5:16]
        kind = o.get('type')

        if o.get('subtype') == 'compact_boundary':
            meta = o.get('compactMetadata') or {}
            c['compactions'].append({'timestamp': ts, 'pre_tokens': meta.get('preTokens'),
                                     'trigger': meta.get('trigger')})
            dg.emit(f'\n## [{t}] COMPACTION preTokens={meta.get("preTokens")} trigger={meta.get("trigger")}')
            return

        if kind == 'queue-operation':
            # enqueue carries the text the user typed. remove repeats it when it is delivered,
            # popAll when the user pulls the waiting messages back, and dequeue carries none.
            op, content = o.get('operation'), o.get('content')
            if op == 'enqueue' and content is not None:
                txt = said(content)
                if txt:
                    queued_sighting(ts, txt, 'enqueue', content if isinstance(content, str) else txt)
            elif op == 'remove' and isinstance(content, str):
                msgs.delivered(content)
            elif op == 'popAll' and isinstance(content, str):
                for m in msgs.withdraw(content, ts):
                    when = m['ts'][5:16]
                    dg.replace(m['line'], f"\n### [{when}] WITHDRAWN LATER (queued while busy, pulled back "
                                          f"at {t}): {m['text'][:3000]}")
                    dg.emit(f"[{t}] WITHDRAWN FROM THE QUEUE (queued {when}): {m['text'][:3000]}")
            return

        if kind == 'attachment':
            a = o.get('attachment') or {}
            if a.get('type') == 'queued_command':
                txt = said(a.get('prompt'))
                ok = origin_kind(a)
                if txt and not a.get('isMeta') and ok in ('human', None):
                    queued_sighting(ts, txt, 'attachment', None)
            return

        msg = o.get('message') or {}
        content = msg.get('content')

        if kind == 'user':
            if o.get('isCompactSummary'):
                c['compaction_summaries'] += 1
                dg.emit(f'[{t}] (compaction summary inserted)')
                return
            if isinstance(content, list) and any(p.get('type') == 'tool_result' for p in content):
                for p in content:
                    if p.get('type') != 'tool_result':
                        continue
                    body = text_of(p.get('content'))
                    denial = o.get('toolDenialKind')
                    if not denial and p.get('is_error'):
                        denial = next((k for k, rx in DENIAL_TEXTS if rx.search(body[:400])), None)
                    if p.get('is_error'):
                        c['tool_errors'] += 1
                    if denial:
                        c['denials'][str(denial)] += 1
                        dg.emit(f'[{t}] DENIED ({denial}): {" ".join(body.split())[:400]}')
                    elif p.get('is_error'):
                        dg.emit(f'[{t}] TOOL-ERROR: {" ".join(body.split())[:400]}')
                return
            txt = said(content)
            if not txt:
                return
            if (o.get('queueOrigin') or {}).get('source') == 'goal-checkin':
                c['goal_notifications'] += 1
            ok = origin_kind(o)
            hk = harness_kind(txt)
            if o.get('isMeta'):
                harness_user_record(ts, hk or 'meta', txt)
            elif ok and ok != 'human':
                harness_user_record(ts, hk or str(ok), txt)
            elif o.get('promptSource') == 'system':
                harness_user_record(ts, hk or 'system', txt)
            elif o.get('scheduledTaskId') or o.get('wakeupSource'):
                harness_user_record(ts, hk or 'scheduled', txt)
            elif hk and ok != 'human':
                system_line(ts, hk, txt, c['system_lines'])
            else:
                cmd = user_command(txt)
                shown = cmd[1] if cmd else txt
                source = o.get('promptSource')
                # A message typed at an idle prompt is new by definition. Only a record that
                # came out of the queue, or an older record with no promptSource, may repeat
                # an earlier sighting.
                user_msg(ts, shown, 'user', source == 'queued', source in ('queued', None), cmd)

        elif kind == 'assistant':
            u = msg.get('usage') or {}
            size = sum(u.get(f) or 0 for f in TOKEN_FIELDS[:3])
            mid = msg.get('id') or o.get('uuid')
            if size and mid not in c['turns']:
                c['turns'][mid] = size
                c['output_tokens'] += u.get('output_tokens') or 0
            for p in content if isinstance(content, list) else ():
                if p.get('type') == 'text' and (p.get('text') or '').strip():
                    dg.emit(f"\n[{t}] ASSISTANT: {p['text']}")
                elif p.get('type') == 'tool_use':
                    i, name = p.get('input') or {}, p.get('name')
                    if name == 'AskUserQuestion':
                        c['asked'] += 1
                        dg.emit(f'[{t}] ASKED THE USER: {str(i)[:600]}')
                    elif name in LAUNCH_TOOLS:
                        role = str(i.get('subagent_type') or '(default)')
                        model = str(i.get('model') or '(inherit)')
                        c['launches'][(role, model)] += 1
                        dg.emit(f"[{t}] LAUNCH {role} {model}: {i.get('description')} :: "
                                f"{str(i.get('prompt', ''))[:700]}")
                    elif name == 'SendMessage':
                        c['sent'] += 1
                        to = i.get('to') or i.get('recipient')
                        body = i.get('message') or i.get('content') or ''
                        dg.emit(f'[{t}] SEND TO {to}: {str(body)[:400]}')
                    elif name == 'Bash':
                        dg.emit(f"[{t}] BASH: {str(i.get('description', ''))[:120]} :: "
                                f"{str(i.get('command', ''))[:260]}")
                    elif name in ('Write', 'Edit'):
                        dg.emit(f"[{t}] {name}: {i.get('file_path')}")
                    else:
                        dg.emit(f'[{t}] TOOL {name}: {str(i)[:200]}')

    with open(args.transcript, encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            done += len(raw)
            if not raw.strip():
                continue
            try:
                o = json.loads(raw)
            except ValueError:
                c['unparsed'] += 1
                continue
            if not isinstance(o, dict):
                c['unparsed'] += 1
                continue
            c['records'] += 1
            if c['records'] % 2000 == 0:
                prog.tick(done, c['records'], len(msgs.items))
            try:
                check_shape(o)
            except Malformed:
                c['malformed'] += 1
                continue
            try:
                record(o)
            except (AttributeError, TypeError, ValueError, KeyError):
                # A shape check_shape does not know yet. The record is skipped and counted, and
                # the run goes on: a partial count beats a traceback with none.
                c['malformed'] += 1
    prog.done()
    return c, msgs


def summary(c, msgs):
    items = msgs.live()
    ctx = sorted(c['turns'].values())
    by_role = collections.defaultdict(dict)
    for (role, model), n in sorted(c['launches'].items()):
        by_role[role][model] = n
    return {
        'span': {'first': c['first'], 'last': c['last']},
        'records': c['records'],
        'unparsed_lines': c['unparsed'],
        'malformed_records': c['malformed'],
        'sidechain_records_skipped': c['sidechain'],
        'compactions': c['compactions'],
        'compaction_summaries': c['compaction_summaries'],
        'user_messages': {
            'total': len(items),
            'typed': sum(1 for m in items if not m['queued']),
            'queued': sum(1 for m in items if m['queued']),
            'slash_commands': sum(1 for m in items if m['command'] and m['command'][0] == 'slash'),
            'shell_commands': sum(1 for m in items if m['command'] and m['command'][0] == 'shell'),
            'duplicates_merged': msgs.merged,
            'late_merges': msgs.late,
            'withdrawn': sum(1 for m in msgs.items if m['state'] == 'withdrawn'),
        },
        'system_lines': dict(sorted(c['system_lines'].items())),
        'queued_system_lines': dict(sorted(c['queued_system_lines'].items())),
        'interrupts': c['interrupts'],
        'questions_to_user': c['asked'],
        'launches': {'total': sum(c['launches'].values()), 'by_role': dict(by_role)},
        'agent_messages_sent': c['sent'],
        'tool_errors': c['tool_errors'],
        'permission_denials': {'total': sum(c['denials'].values()), 'by_kind': dict(sorted(c['denials'].items()))},
        'stop_hook_prompts': c['stop_hook'],
        'goal_checks': {'feedback': c['goal_feedback'], 'notifications': c['goal_notifications']},
        'assistant_turns': len(ctx),
        'context_median': ctx[len(ctx) // 2] if ctx else 0,
        'context_max': ctx[-1] if ctx else 0,
        'output_tokens': c['output_tokens'],
    }


def print_text(s):
    um = s['user_messages']
    print(f"span: {s['span']['first']} to {s['span']['last']}")
    print(f"records: {s['records']}, unparsed lines: {s['unparsed_lines']}, "
          f"malformed records: {s['malformed_records']}, "
          f"sidechain records skipped: {s['sidechain_records_skipped']}")
    print(f"compactions: {len(s['compactions'])} (summaries inserted: {s['compaction_summaries']})")
    for cp in s['compactions']:
        print(f"  {cp['timestamp']}  preTokens={cp['pre_tokens']}  trigger={cp['trigger']}")
    print(f"user messages: {um['total']} (typed {um['typed']}, queued while busy {um['queued']}; "
          f"slash commands {um['slash_commands']}, shell commands {um['shell_commands']}; "
          f"duplicates merged {um['duplicates_merged']}, of them late {um['late_merges']})")
    print(f"withdrawn from the queue: {um['withdrawn']}")
    print('system lines: ' + (', '.join(f'{k} {v}' for k, v in s['system_lines'].items()) or 'none'))
    print('queued system lines: ' + (', '.join(f'{k} {v}' for k, v in s['queued_system_lines'].items()) or 'none'))
    print(f"interrupts: {s['interrupts']}, questions to the user: {s['questions_to_user']}")
    print(f"subagent launches: {s['launches']['total']}")
    for role, models in sorted(s['launches']['by_role'].items()):
        for model, n in sorted(models.items()):
            print(f'  {role} on {model}: {n}')
    print(f"messages sent to running agents: {s['agent_messages_sent']}")
    pd = s['permission_denials']
    print(f"tool errors: {s['tool_errors']}, permission denials: {pd['total']}"
          + (' (' + ', '.join(f'{k} {v}' for k, v in pd['by_kind'].items()) + ')' if pd['by_kind'] else ''))
    print(f"stop-hook prompts: {s['stop_hook_prompts']}, goal check feedback: {s['goal_checks']['feedback']}, "
          f"goal check notifications: {s['goal_checks']['notifications']}")
    print(f"assistant turns: {s['assistant_turns']}, context median {s['context_median']}, "
          f"max {s['context_max']}; output tokens {s['output_tokens']}")


def main():
    ap = argparse.ArgumentParser(description='Count one Claude Code session transcript and write a digest.')
    ap.add_argument('transcript')
    ap.add_argument('--out', help='write the chronological digest to this file')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--json', action='store_true', help='print the counts as one JSON object')
    mode.add_argument('--user-messages', action='store_true',
                      help="print every message counted as the user's, one per line")
    ap.add_argument('--dedupe-seconds', type=float, default=300,
                    help='merge sightings of one queued message within this many seconds (0 turns it off)')
    ap.add_argument('--report-chars', type=int, default=2500,
                    help='characters of an agent report kept in the digest')
    ap.add_argument('--quiet', action='store_true', help='no progress lines on stderr')
    args = ap.parse_args()

    if not os.path.isfile(args.transcript) or not os.access(args.transcript, os.R_OK):
        print(f'transcript-digest: cannot read {args.transcript}', file=sys.stderr)
        return 2

    dg = Digest(bool(args.out))
    try:
        c, msgs = scan(args, dg)
    except KeyboardInterrupt:
        print('\ntranscript-digest: interrupted. Nothing is saved; run it again from the start.',
              file=sys.stderr)
        return 130
    if args.out:
        dg.write(args.out)

    if args.user_messages:
        for m in sorted(msgs.live(), key=lambda m: m['ts']):
            text = ' '.join(m['text'].replace('\t', ' ').splitlines())[:200]
            print(f"{m['ts']}\t{'queued' if m['queued'] else 'typed'}\t{text}")
        return 0
    s = summary(c, msgs)
    if args.json:
        print(json.dumps(s, sort_keys=True))
    else:
        print_text(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
