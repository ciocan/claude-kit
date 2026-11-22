#!/usr/bin/env python3
"""Tick or untick checkboxes in a GitHub issue body, with a backup and a guard on every byte.

Usage:
  tick.py <issue> (--all | --match <text>... | --line <n>...) [options]

  --all                  every unticked box
  --match <text>         the one box whose line holds <text>, a fixed string, not a regex.
                         Repeatable. The text must hit exactly one box, ticked or not. If that
                         box is already ticked, it is reported and skipped. A text that hits
                         two boxes is a refusal even when only one of them is open: with one
                         open and one ticked box both matching, the open one may not be the box
                         that was meant, and a rerun of --match "#412" must never tick "#4123"
  --line <n>             the n-th checkbox in the body, counting from 1. Repeatable
  --untick               reverse the direction of all three
  --repo <owner/repo>    passed to every gh call. Default: gh's own (the current repository)
  --dry-run              show the lines that would change, edit nothing
  --backup-dir <dir>     where the body is saved before the edit

A box is a list item with [ ], [x] or [X]: a bullet (-, *, +) or an ordered marker (1. or 1)),
indented or inside a quote (> ). Lines inside a code fence (``` or ~~~) are never boxes, so
template text is left alone. A box in a code block made by indentation alone is still counted.

The body comes from `gh issue view <n> --json body` and is parsed from the JSON, so it is the
body as stored, byte for byte. The shell version read it with `gh -q .body`, which prints the
body and then a newline of its own, and had to drop that byte, or every edit would have added a
line end to the issue. The body is handled as bytes: CRLF line ends, a missing final newline and
every other byte survive.

Saves the body as <backup-dir>/issue-<n>-<yyyymmddThhmmssZ>.before.md (-2, -3 when taken) and
edits only when the edited body has the same lines and bytes and differs in nothing but the
bracket character of the selected boxes. The edit is sent with `gh issue edit --body-file` from
<stem>.after.md. After the edit it reads the body back and compares, and on a mismatch prints
the command that restores the backup. No file is read and written at once: the body is held in
memory, the backup and the edit file are each written once from bytes that passed the guards,
and the read-back is compared in memory. A helper that read and wrote one file in one shell
expression got an empty file to read, sent it up, and blanked eleven issue bodies.

Two runs on one machine never interleave: each run holds an flock on
<backup-dir>/.issue-<n>.lock from the first read to the read-back, and waits up to
TICK_LOCK_WAIT_S seconds for it. Just before the edit it reads the body once more and refuses if
it changed since the backup, so a box someone else ticked meanwhile is not undone. That second
read narrows the window and cannot close it: GitHub has no conditional update, so an edit made in
a browser or on another machine between that read and the edit is overwritten.

On success only the backup is kept. When a run exits 3, the .after.md file it sent is kept beside
the backup, and so is a .readback.md when the body read back differs from it.

Exit codes: 0 done or nothing to do, 1 refused by a guard or by the selection, or another run
            holds the issue, 2 usage, 3 the body read back differs from what was sent,
            130 stopped by INT or TERM (after the cleanup).
Env: TICK_BACKUP_DIR   backup dir when --backup-dir is not given
                       (default ${XDG_STATE_HOME:-$HOME/.local/state}/claude-kit/issue-bodies)
     TICK_LOCK_WAIT_S  seconds to wait for another run on the same issue (default 30)
"""
import difflib
import errno
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

# The one definition of a box line: optional space, quote marks, a bullet or an ordered marker,
# then the brackets. Group 1 is the bracket character.
BOX_RE = re.compile(rb'[ \t\r\f\v]*(?:>[ \t]*)*(?:[-*+]|[0-9]+[.)]) \[([ xX])\] ')
FENCE_RE = re.compile(rb'[ \t]*(?:>[ \t]*)*(?:```|~~~)')
NUMBER_RE = re.compile(r'[0-9]+(?:[.][0-9]+)?\Z')
DIGITS_RE = re.compile(r'[0-9]+\Z')
SPACE = b' \t\n\r\x0b\x0c'
USAGE_LINE = ('usage: tick.py <issue> (--all | --match <text>... | --line <n>...) '
              '[--repo <owner/repo>] [--untick] [--dry-run] [--backup-dir <dir>]')


class Stop(Exception):
    """End the run: a message for stderr, and an exit code."""

    def __init__(self, code, message=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def refuse(message):
    raise Stop(1, 'tick.py: refused: %s. Nothing was edited.' % message)


def die2(message):
    raise Stop(2, 'tick.py: %s\n%s' % (message, USAGE_LINE))


def out(*parts):
    sys.stdout.buffer.write(b''.join(p if isinstance(p, bytes) else os.fsencode(p)
                                     for p in parts) + b'\n')
    sys.stdout.buffer.flush()


def err(*parts):
    sys.stderr.buffer.write(b''.join(p if isinstance(p, bytes) else os.fsencode(p)
                                     for p in parts) + b'\n')
    sys.stderr.buffer.flush()


# The body as lines, and the boxes in it.

def split_lines(body):
    """Lines the way awk saw them: split at \\n, no empty last line after a final newline."""
    lines = body.split(b'\n')
    if lines[-1] == b'':
        lines.pop()
    return lines


def box_states(lines):
    """For each line, the bracket character of its box, or None when it is not a box.

    A line that opens or closes a code fence flips the fence, and no line inside one is a box.
    """
    states = []
    in_fence = False
    for line in lines:
        state = None
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = BOX_RE.match(line)
            if m:
                state = m.group(1)
        states.append(state)
    return states


def show(line):
    return line.replace(b'\r', b'')


def build_edit(body, selected, want):
    """The body with the bracket character of each selected line (1-based) set to want."""
    edited = bytearray(body)
    offset = 0
    starts = []
    for line in body.split(b'\n'):
        starts.append(offset)
        offset += len(line) + 1
    lines = body.split(b'\n')
    for number in selected:
        m = BOX_RE.match(lines[number - 1])
        if m:
            at = starts[number - 1] + m.start(1)
            edited[at:at + 1] = want
    return bytes(edited)


def check_edit(before, after, selected, want):
    """The guard: after differs from before only in the bracket character of the selected boxes,
    in the wanted direction.

    Returns (bad, refusal): the BAD lines to print and the refusal, or ([], None) when it holds.
    """
    if not after:
        return [], 'the edited body is empty'
    lines_a, lines_b = before.count(b'\n'), after.count(b'\n')
    if lines_a != lines_b:
        return [], 'the edited body has %d lines, the original %d' % (lines_b, lines_a)
    if len(before) != len(after):
        return [], 'the edited body has %d bytes, the original %d' % (len(after), len(before))
    bad, changed = [], []
    old, new = split_lines(before), split_lines(after)
    for number, a in enumerate(old, 1):
        if number > len(new):
            bad.append('BAD line %d: the edited body ends early' % number)
            break
        b = new[number - 1]
        if a == b:
            continue
        m = BOX_RE.match(a)
        if not m:
            bad.append('BAD line %d: not a checkbox line' % number)
            continue
        p = m.start(1)
        if a[:p] != b[:p] or a[p + 1:] != b[p + 1:]:
            bad.append('BAD line %d: more than the bracket character changed' % number)
            continue
        ca, cb = a[p:p + 1], b[p:p + 1]
        from_ok = ca == b' ' if want == b'x' else ca != b' '
        if cb != want or not from_ok:
            bad.append('BAD line %d: [%s] became [%s]' % (number, ca.decode('latin-1'),
                                                          cb.decode('latin-1')))
            continue
        changed.append(number)
    if bad:
        return bad, 'the edited body changes more than the selected boxes'
    got, wanted = sorted(changed), sorted(selected)
    if got != wanted:
        return [], 'the edited body changes lines %s, the selection is lines %s' % (
            ' '.join(map(str, got)) or 'none', ' '.join(map(str, wanted)))
    return [], None


# gh.

def fetch(issue, repo_args, quiet=False):
    """The body as stored, as bytes, or None when gh fails or prints no body."""
    try:
        proc = subprocess.run(['gh', 'issue', 'view', issue] + repo_args + ['--json', 'body'],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL if quiet else None)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        body = json.loads(proc.stdout.decode('utf-8'))['body']
        return body.encode('utf-8')
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        return None


# The per-issue lock.

def take_lock(path, wait_s):
    """Hold an flock on path, waiting up to wait_s seconds. Returns the descriptor."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:
            raise Stop(1, 'tick.py: cannot create the lock file %s: %s. Nothing was edited.'
                       % (path, e.strerror))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise Stop(1, 'tick.py: cannot lock %s: %s. Nothing was edited.'
                           % (path, e.strerror))
            if time.monotonic() >= deadline:
                raise Stop(1, 'tick.py: another writer holds %s (pid %s). Nothing was edited.'
                           % (path, holder(path)))
            time.sleep(0.1)
            continue
        # The run before us removes the file before it lets go. If it did that after our open,
        # we hold a file nobody else will open: start again on the one at the path now.
        try:
            same = os.path.samestat(os.fstat(fd), os.stat(path))
        except OSError:
            same = False
        if not same:
            os.close(fd)
            continue
        try:
            os.ftruncate(fd, 0)
            os.write(fd, b'%d\n' % os.getpid())
        except OSError:
            pass
        return fd


def holder(path):
    try:
        with open(path, 'rb') as f:
            pid = f.read().strip().decode('ascii')
    except (OSError, UnicodeDecodeError):
        return 'unknown'
    return pid if pid.isdigit() else 'unknown'


class Run:
    """Files and the lock that cleanup handles when the run ends."""
    lock = None     # (fd, path)
    files = []      # the backup and its siblings, removed unless the edit went out
    edited = False


def write_new(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def cleanup():
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        if not Run.edited:
            for path in Run.files:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        if Run.lock:
            fd, path = Run.lock
            Run.lock = None
            try:
                os.unlink(path)
            except OSError:
                pass
            os.close(fd)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def on_signal(signum, frame):
    raise SystemExit(130)


def parse(argv):
    issue = repo = backup_dir = ''
    mode = None
    untick = dry = False
    matches, picks = [], []

    def set_mode(m):
        nonlocal mode
        if mode and mode != m:
            die2('use one selector: --all, --match or --line')
        mode = m

    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a == '--all':
            set_mode('all')
            i += 1
        elif a == '--match':
            if not nxt:
                die2('--match needs a text')
            set_mode('match')
            matches.append(os.fsencode(nxt))
            i += 2
        elif a == '--line':
            if nxt is None:
                die2('--line needs a number')
            if not DIGITS_RE.match(nxt):
                die2("--line needs a number from 1, not '%s'" % nxt)
            if int(nxt, 10) < 1:
                die2('--line counts from 1')
            set_mode('line')
            picks.append(int(nxt, 10))
            i += 2
        elif a == '--repo':
            if not nxt:
                die2('--repo needs <owner/repo>')
            repo = nxt
            i += 2
        elif a == '--untick':
            untick = True
            i += 1
        elif a == '--dry-run':
            dry = True
            i += 1
        elif a == '--backup-dir':
            if not nxt:
                die2('--backup-dir needs a directory')
            backup_dir = nxt
            i += 2
        elif a in ('-h', '--help'):
            sys.stderr.write(__doc__)
            raise Stop(2)
        elif a.startswith('-'):
            die2('unknown option: %s' % a)
        else:
            if issue:
                die2('one issue at a time')
            issue = a[1:] if a.startswith('#') else a
            i += 1
    if not issue:
        die2('no issue number')
    if not DIGITS_RE.match(issue):
        die2("the issue must be a number, not '%s'" % issue)
    if not mode:
        die2('no selector: pass --all, --match <text> or --line <n>')
    return issue, repo, backup_dir, mode, untick, dry, matches, picks


def tick(argv):
    Run.lock, Run.files, Run.edited = None, [], False
    issue, repo, backup_dir, mode, untick, dry, matches, picks = parse(argv)
    if not shutil.which('gh'):
        raise Stop(2, 'tick.py: gh is required')
    wait = os.environ.get('TICK_LOCK_WAIT_S') or '30'
    if not NUMBER_RE.match(wait):
        die2("TICK_LOCK_WAIT_S must be a number of seconds, not '%s'" % wait)

    repo_args = ['--repo', repo] if repo else []
    verb, want = ('untick', b' ') if untick else ('tick', b'x')

    # 1. Lock the issue, then back up the body. O_EXCL never lets a run overwrite an earlier
    # backup.
    state = os.environ.get('XDG_STATE_HOME') or os.environ.get('HOME', '') + '/.local/state'
    bdir = backup_dir or os.environ.get('TICK_BACKUP_DIR') or state + '/claude-kit/issue-bodies'
    try:
        os.makedirs(bdir, exist_ok=True)
    except OSError:
        raise Stop(1, 'tick.py: cannot create %s' % bdir)
    lock = '%s/.issue-%s.lock' % (bdir, issue)
    Run.lock = (take_lock(lock, float(wait)), lock)

    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    stem = '%s/issue-%s-%s' % (bdir, issue, stamp)
    k = 1
    while True:
        try:
            fd = os.open(stem + '.before.md', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            break
        except FileExistsError:
            k += 1
            stem = '%s/issue-%s-%s-%d' % (bdir, issue, stamp, k)
        except OSError:
            raise Stop(1, 'tick.py: cannot write in %s' % bdir)
    before_path, after_path, back_path = (stem + '.before.md', stem + '.after.md',
                                          stem + '.readback.md')
    Run.files = [before_path, after_path, back_path]
    restore = 'gh issue edit %s%s --body-file %s' % (
        issue, ' --repo ' + shlex.quote(repo) if repo else '', shlex.quote(before_path))

    before = fetch(issue, repo_args)
    if before is None:
        os.close(fd)
        refuse('cannot read the body of #%s' % issue)
    try:
        view = memoryview(before)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    if not before.strip(SPACE):
        refuse('the body of #%s is empty' % issue)

    # 2. Find the boxes.
    lines = split_lines(before)
    states = box_states(lines)
    boxes = [(n, s) for n, s in enumerate(states, 1) if s is not None]
    total = len(boxes)
    if total == 0:
        refuse('#%s has no checkboxes' % issue)

    def is_source(s):
        return s != b' ' if untick else s == b' '

    done_word = 'already unticked' if untick else 'already ticked'
    selected = []

    def pick(n):
        if n not in selected:
            selected.append(n)

    # 3. Select.
    problems = []
    if mode == 'all':
        for n, s in boxes:
            if is_source(s):
                pick(n)
    elif mode == 'line':
        for p in picks:
            if p > total:
                problems.append('--line %d: #%s has %d checkboxes' % (p, issue, total))
                continue
            n, s = boxes[p - 1]
            if is_source(s):
                pick(n)
            else:
                out('%s, skipped: line %d: ' % (done_word, n), show(lines[n - 1]))
    else:
        for text in matches:
            hits = [(n, s) for n, s in boxes if text in lines[n - 1]]
            src = [n for n, s in hits if is_source(s)]
            oth = [n for n, s in hits if not is_source(s)]
            shown = os.fsdecode(text)
            if not hits:
                problems.append("--match '%s' fits no box" % shown)
            elif len(hits) > 1:
                problems.append("--match '%s' fits %d boxes, make it unique:" % (shown, len(hits)))
                for n in src + oth:
                    problems.append(b'  line %d: ' % n + show(lines[n - 1]))
            elif src:
                pick(src[0])
            else:
                out('%s, skipped: line %d: ' % (done_word, oth[0]), show(lines[oth[0] - 1]))
    if problems:
        for p in problems:
            err(p)
        refuse('the selection did not hold')
    if not selected:
        out('nothing to %s in #%s' % (verb, issue))
        return 0

    # 4. Build the edited body, and 5. hold it to the guard.
    after = build_edit(before, selected, want)
    bad, refusal = check_edit(before, after, selected, want)
    if refusal:
        for line in bad:
            err(line)
        refuse(refusal)
    after_lines = split_lines(after)

    if dry:
        for n in sorted(selected):
            out('line %d: ' % n, show(lines[n - 1]))
            out('     now: ', show(after_lines[n - 1]))
        out('dry run: would %s %d of %d boxes in #%s, nothing edited'
            % (verb, len(selected), total, issue))
        return 0

    # 6. Read the body once more. If someone changed it since the backup, an edit built from the
    # backup would undo their change.
    again = fetch(issue, repo_args)
    if again is None:
        refuse('cannot read the body of #%s again before the edit' % issue)
    if again != before:
        refuse('the body of #%s changed since it was read, run again to work from the new body'
               % issue)

    # 7. Edit, then believe only what reads back.
    write_new(after_path, after)
    Run.edited = True
    proc = subprocess.run(['gh', 'issue', 'edit', issue] + repo_args + ['--body-file', after_path],
                          stdout=subprocess.DEVNULL)
    if proc.returncode != 0:
        back = fetch(issue, repo_args, quiet=True)
        if back == before:
            Run.edited = False
            refuse('the edit call failed and the body is as it was')
        raise Stop(3, 'tick.py: the edit call failed and the body may have changed. Restore it '
                      'with:\n  %s' % restore)
    back = fetch(issue, repo_args)
    if back is None:
        raise Stop(3, 'tick.py: edited #%s, but cannot read it back. Check it, and restore it if '
                      'needed with:\n  %s' % (issue, restore))
    if back != after:
        write_new(back_path, back)
        diff = list(difflib.unified_diff(
            after.decode('utf-8', 'replace').splitlines(),
            back.decode('utf-8', 'replace').splitlines(), 'sent', 'read back', lineterm=''))
        err('tick.py: the body of #%s read back differs from what was sent:' % issue)
        for line in diff[:20]:
            err('  ' + line)
        raise Stop(3, 'Sent: %s. Read back: %s. Restore the original with:\n  %s'
                   % (after_path, back_path, restore))
    for path in (after_path, back_path):
        try:
            os.unlink(path)
        except OSError:
            pass
    out('%sed %d of %d boxes in #%s, backup %s' % (verb, len(selected), total, issue, before_path))
    return 0


def main(argv):
    try:
        return tick(argv)
    except Stop as e:
        if e.message:
            err(e.message)
        return e.code
    finally:
        cleanup()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    sys.exit(main(sys.argv[1:]))
