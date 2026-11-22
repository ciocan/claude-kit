#!/usr/bin/env python3
"""Keep a program note's log: stamp every entry from the machine's clock, and rotate the log.

Usage:
  note.py add    <note-file> <bullet text>...   one bullet per argument. A single "-" reads
                                                the bullets from stdin, one per line
  note.py rotate <note-file> --summary <text>... [--carry <text>...] [--dry-run]
  note.py check  <note-file>
  note.py now

The log is everything from the first "## yyyy-mm-dd hh:mm UTC" heading to the end of the file.
Everything above it is the top block, and this script never changes it. The format is in
references/program-note.md.

add     appends one entry stamped with the current UTC time. There is no way to pass a time.
        Warns on stderr when the log has grown past NOTE_MAX_LINES lines.
rotate  moves the log to <note>-log-<yyyy-mm-dd>.md next to the note (-2, -3 when taken) and
        leaves one entry: where the log went, one to five --summary bullets, then a --carry
        bullet for each live item (running jobs, agents, holds, what the user owes).
check   prints the log's size, its first and last stamps, and the entries that go back in time.
        Exits 1 when the log is over the limit or a stamp goes back in time.
now     prints the stamp add would use.

One writer at a time. add and rotate hold an flock on <dir>/.<note>.lock while they read and
write, and read the clock only once they hold it, so entries land in the order of their stamps.
Without the lock, two adds at once each copied the note, appended to the copy and moved it into
place, and the second move threw the first entry away while both runs reported success. The kernel
drops an flock when its process dies, so a killed run never leaves a lock that blocks the next
one. The lock is not a mkdir: where coreutils is the Rust rewrite (uutils 0.10), two mkdir calls
on one path at the same moment can both exit 0. A note that is a symlink is followed: the target
is written and the link stays.

How each command writes:
  add     appends in place, in one write on a descriptor opened with O_APPEND, then reads the
          bytes back at the offset the write ended on. An editor or another tool that appends
          without the lock keeps its lines: nothing is copied and moved over them.
  rotate  writes the archive first (created with O_EXCL and the note's own mode, then fsynced and
          read back), then the new note into a temp file next to the note (fsynced and compared
          byte for byte with the top block plus the new entry), checks the note has not changed
          since it was read, and renames the temp file over the note. rotate never opens the
          note for writing: a truncating open empties it before anything reads it, which is how
          a shell helper once lost a whole file. Once the archive is complete and verified,
          nothing deletes it. A failure or a TERM after that leaves both the archive and the
          unchanged note, which loses nothing.
  The rename cannot wait for a writer that takes no lock. A line an editor appends between the
  last comparison and the rename is lost. No check can close that window, so do not edit the note
  by hand while a rotate runs.

Exit codes: 0 ok, 1 a check failed or nothing could be written, 2 usage, 130 stopped by INT or
            TERM (after the cleanup).
Env: NOTE_MAX_LINES    log lines before add warns and check fails (default 300)
     NOTE_LOCK_WAIT_S  seconds to wait for another writer before giving up (default 10)
     NOTE_NOW          replaces the clock. It exists for tests only and a session must never set
                       it: times typed from memory are what this script is here to stop.
"""
import errno
import fcntl
import os
import re
import signal
import stat
import sys
import tempfile
import time

# A log heading starts a line. Text after "UTC" is allowed, as before.
HEADING_RE = re.compile(rb'## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC')
STAMP_RE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC\Z')
NUMBER_RE = re.compile(r'[0-9]+(?:[.][0-9]+)?\Z')
WHOLE_RE = re.compile(r'[0-9]+\Z')
SPACE = b' \t\n\r\x0b\x0c'


class Failure(Exception):
    """Stop with a message on stderr and an exit code."""

    def __init__(self, message, code=1):
        Exception.__init__(self, message)
        self.message = message
        self.code = code


class State:
    """What cleanup must undo when the run ends early."""
    tmps = []            # temp files to remove
    own_archive = None   # an archive still being written: removed on failure
    kept_archive = None  # an archive complete and verified: never removed
    lock = None          # (fd, path) of the held lock


def out(*parts):
    """Write one line to stdout. Parts are str or bytes, joined as given."""
    sys.stdout.buffer.write(b''.join(p if isinstance(p, bytes) else os.fsencode(p)
                                     for p in parts) + b'\n')
    sys.stdout.buffer.flush()


def err(*parts):
    sys.stderr.buffer.write(b''.join(p if isinstance(p, bytes) else os.fsencode(p)
                                     for p in parts) + b'\n')
    sys.stderr.buffer.flush()


def usage():
    sys.stderr.write(__doc__)
    sys.exit(2)


def die2(message):
    raise Failure(message, 2)


def fail(message):
    """A write that did not happen. The note is as it was."""
    message += '. The note is unchanged'
    if State.kept_archive:
        message += '. Its log is also in %s' % State.kept_archive
    raise Failure(message + '.', 1)


# The clock.

def utc_stamp():
    """The machine's clock as a stamp, always in UTC."""
    return time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())


def read_stamp():
    """The stamp for an entry, or Failure: an entry without a real time is worse than none."""
    stamp = os.environ.get('NOTE_NOW', '')
    if not stamp:
        try:
            stamp = utc_stamp()
        except (OSError, ValueError, OverflowError):
            stamp = ''
    if not isinstance(stamp, str) or not STAMP_RE.match(stamp):
        raise Failure("no valid time from the clock (got '%s'). Nothing was written." % stamp, 1)
    return stamp


# Lines, the way grep and awk saw them: split at \n, and a last line without its newline counts.

def split_lines(data):
    lines = data.split(b'\n')
    if lines[-1] == b'':
        lines.pop()
    return lines


def first_entry(lines):
    """Index of the first log heading, or None."""
    for i, line in enumerate(lines):
        if HEADING_RE.match(line):
            return i
    return None


def one_line(text):
    return text.replace(b'\r', b' ').replace(b'\n', b' ')


def entry_bytes(stamp, bullets, note_size, last_byte):
    """What add appends: a blank line, the heading and the bullets.

    A note whose last line has no newline gets one first, so it does not swallow the blank line.
    """
    head = b'\n'
    if note_size > 0 and last_byte != b'\n':
        head = b'\n\n'
    return head + b'## ' + stamp.encode() + b'\n' + b''.join(b + b'\n' for b in bullets)


def new_note_matches(written, top, entry_lines):
    """The guard on rotate's new note: exactly the old top block, then the new entry."""
    return written == top + b''.join(line + b'\n' for line in entry_lines)


# Files.

def read_file(path):
    with open(path, 'rb') as f:
        return f.read()


def write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def write_temp(folder, file, mode, data):
    """A new temp file next to the note, with the note's mode, holding data, fsynced."""
    fd, path = tempfile.mkstemp(prefix='.%s.' % file, dir=folder)
    State.tmps.append(path)
    try:
        os.fchmod(fd, mode)
        write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def fsync_dir(folder):
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def dirname(path):
    return os.path.dirname(path) or '.'


def open_note(path):
    """The note's real path, its folder, its file name and its base name."""
    note = path
    if not os.path.isfile(note):
        die2('note not found: %s (note.py does not create notes)' % note)
    # Follow a symlink to the file it names. A rename over the link would replace the link, and
    # the real note would stop receiving entries.
    hops = 0
    while os.path.islink(note) and hops < 8:
        link = os.readlink(note)
        note = link if link.startswith('/') else dirname(note) + '/' + link
        hops += 1
    file = os.path.basename(note)
    base = file[:-3] if file.endswith('.md') else file
    return note, dirname(note), file, base


# The lock.

def lock_wait():
    wait = os.environ.get('NOTE_LOCK_WAIT_S') or '10'
    if not NUMBER_RE.match(wait):
        die2("NOTE_LOCK_WAIT_S must be a number of seconds, not '%s'" % wait)
    return float(wait)


def take_lock(path, wait_s):
    """Hold an flock on path, waiting up to wait_s seconds for another writer."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:
            raise Failure('cannot create the lock file %s: %s. Nothing was written.'
                          % (path, e.strerror), 1)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise Failure('cannot lock %s: %s. Nothing was written.' % (path, e.strerror), 1)
            if time.monotonic() >= deadline:
                raise Failure('another writer holds %s (pid %s). Nothing was written.'
                              % (path, holder(path)), 1)
            time.sleep(0.1)
            continue
        # The writer before us removes the file before it lets go. If it did that after our open,
        # we hold a file nobody else will open: start again on the one at the path now.
        try:
            same = os.path.samestat(os.fstat(fd), os.stat(path))
        except OSError:
            same = False
        if not same:
            os.close(fd)
            continue
        State.lock = (fd, path)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, b'%d\n' % os.getpid())
        except OSError:
            pass
        return


def holder(path):
    """The pid the holder wrote in the lock file, for the message."""
    try:
        pid = read_file(path).strip().decode('ascii')
    except (OSError, UnicodeDecodeError):
        return 'unknown'
    return pid if pid.isdigit() else 'unknown'


def release_lock():
    if State.lock is None:
        return
    fd, path = State.lock
    State.lock = None
    # Remove the file while still holding it. A writer that opened it before the removal finds
    # that the path no longer names its file once it gets the lock, and starts again.
    try:
        os.unlink(path)
    except OSError:
        pass
    os.close(fd)


def cleanup():
    # A second TERM must not cut the cleanup short. It is held until the end.
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        undo()
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def undo():
    for path in State.tmps:
        try:
            os.unlink(path)
        except OSError:
            pass
    State.tmps = []
    if State.own_archive:
        try:
            os.unlink(State.own_archive)
        except OSError:
            pass
        State.own_archive = None
    release_lock()


def on_signal(signum, frame):
    raise SystemExit(130)


# The commands.

def cmd_add(args, max_lines):
    note, folder, file, _ = open_note(args[0])
    raw = args[1:]
    if len(raw) == 1 and raw[0] == '-':
        raw = sys.stdin.buffer.read().split(b'\n')
    else:
        raw = [os.fsencode(a) for a in raw]
    bullets = []
    for b in raw:
        b = one_line(b)
        if not b.strip(SPACE):
            continue
        if not b.startswith(b'- '):
            b = b'- ' + b
        bullets.append(b)
    if not bullets:
        die2('no bullet to add')

    take_lock('%s/.%s.lock' % (folder, file), lock_wait())
    stamp = read_stamp()
    try:
        fd = os.open(note, os.O_RDWR | os.O_APPEND)
    except OSError as e:
        fail('cannot open %s: %s' % (note, e.strerror))
    try:
        size = os.fstat(fd).st_size
        last = os.pread(fd, 1, size - 1) if size > 0 else b''
        entry = entry_bytes(stamp, bullets, size, last)
        # One write: with O_APPEND the kernel puts it at the end of the file as it is at that
        # moment, after anything another writer appended.
        try:
            wrote = os.write(fd, entry)
        except OSError as e:
            fail('cannot append to %s: %s' % (note, e.strerror))
        end = os.lseek(fd, 0, os.SEEK_CUR)
        if wrote != len(entry):
            raise Failure('only %d of %d bytes of the entry reached %s. Check the note.'
                          % (wrote, len(entry), note), 1)
        os.fsync(fd)
        # Believe the note, not the write: the entry must be there, where the write ended.
        if os.pread(fd, len(entry), end - len(entry)) != entry:
            raise Failure('the entry is not where it was written in %s. Check the note.'
                          % note, 1)
    finally:
        os.close(fd)
    lines = split_lines(read_file(note))
    release_lock()

    start = first_entry(lines)
    n = len(lines) - (start if start is not None else len(lines))
    out('added %d lines at %s (log %d lines)' % (len(bullets), stamp, n))
    if n > max_lines:
        err('note.py: the log is %d lines, over %d. Rotate it: note.py rotate %s --summary "..."'
            % (n, max_lines, note))
    return 0


def cmd_check(args, max_lines):
    note = open_note(args[0])[0]
    data = read_file(note)
    kb = (len(data) + 1023) // 1024
    lines = split_lines(data)
    start = first_entry(lines)
    if start is None:
        out('no log entries in %s (%d KB)' % (note, kb))
        return 0
    n = len(lines) - start
    out('log: %d lines, limit %d%s' % (n, max_lines, ', OVER THE LIMIT' if n > max_lines else ''))
    out('note: %d KB' % kb)
    stamps = [(i + 1, line) for i, line in enumerate(lines) if HEADING_RE.match(line)]
    bad = []
    prev = None
    for number, line in stamps:
        s = line[3:23]
        if prev is not None and s < prev:
            bad.append((number, line))
        prev = s
    out(b'entries: %d, first %s, last %s' % (len(stamps), stamps[0][1][3:23], stamps[-1][1][3:23]))
    out('out of order: %d' % len(bad))
    for number, line in bad:
        out(b'  line %d: ' % number, line)
    return 0 if n <= max_lines and not bad else 1


def cmd_rotate(args):
    note, folder, file, base = open_note(args[0])
    summaries, carries, dry = [], [], False
    rest = args[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ('--summary', '--carry'):
            if i + 1 >= len(rest) or not os.fsencode(rest[i + 1]).strip(SPACE):
                die2('%s needs a text' % a)
            (summaries if a == '--summary' else carries).append(one_line(os.fsencode(rest[i + 1])))
            i += 2
        elif a == '--dry-run':
            dry = True
            i += 1
        else:
            die2('unknown rotate option: %s' % a)
    if not summaries:
        die2('rotate needs at least one --summary (what the period achieved, what it left open)')
    if len(summaries) > 5:
        die2('at most five --summary lines, got %d' % len(summaries))

    if not dry:
        take_lock('%s/.%s.lock' % (folder, file), lock_wait())
    stamp = read_stamp()
    data = read_file(note)
    lines = split_lines(data)
    start = first_entry(lines)
    if start is None:
        out('nothing to rotate')
        return 0
    total = len(lines)
    n = total - start
    day = stamp.split(' ')[0]
    name = '%s-log-%s.md' % (base, day)
    k = 1
    while os.path.lexists('%s/%s' % (folder, name)):
        k += 1
        name = '%s-log-%s-%d.md' % (base, day, k)
    entry = [b'## ' + stamp.encode(),
             os.fsencode('- Rotated: %d log lines up to here moved to %s' % (n, name))]
    entry += [b'- Summary: ' + s for s in summaries]
    entry += [b'- Carried forward: ' + c for c in carries]

    if dry:
        out('dry run: would move %d log lines (lines %d to %d) to %s/%s'
            % (n, start + 1, total, folder, name))
        out('the top block (%d lines) stays, followed by this entry:' % start)
        for line in entry:
            out(b'  ', line)
        return 0

    cut = sum(len(line) + 1 for line in lines[:start])
    top, log = data[:cut], data[cut:]
    mode = stat.S_IMODE(os.stat(note).st_mode) & 0o777

    # 1. The archive. O_EXCL refuses a file that appeared meanwhile. It gets the note's own mode
    # from the start, so a private note never has a readable archive, not even for a moment.
    rotated = '%s/%s' % (folder, name)
    archive = os.fsencode('# %s log, rotated %s\n\n' % (base, stamp)) + log
    try:
        fd = os.open(rotated, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    except OSError as e:
        fail('cannot create %s: %s' % (rotated, e.strerror))
    State.own_archive = rotated
    try:
        os.fchmod(fd, mode)
        write_all(fd, archive)
        os.fsync(fd)
    except OSError as e:
        fail('cannot write %s: %s' % (rotated, e.strerror))
    finally:
        os.close(fd)
    try:
        if read_file(rotated) != archive:
            fail('the archive %s does not hold the %d log lines' % (rotated, n))
    except OSError as e:
        fail('cannot read back %s: %s' % (rotated, e.strerror))
    # Complete and verified. From here on nothing deletes it, whatever happens to the note.
    State.kept_archive = rotated
    State.own_archive = None

    # 2. The new note, in a temp file next to it, so the rename stays on one file system.
    try:
        tmp = write_temp(folder, file, mode, top + b''.join(line + b'\n' for line in entry))
        written = read_file(tmp)
    except OSError as e:
        fail('cannot write the new note next to %s: %s' % (note, e.strerror))
    if not new_note_matches(written, top, entry):
        fail('the new note is not the top block followed by the new entry')

    # 3. The swap. The note must still be what was read, or the rename would drop new lines.
    try:
        if read_file(note) != data:
            fail('the note changed while rotating')
        os.replace(tmp, note)
    except OSError as e:
        fail('cannot move the new note over %s: %s' % (note, e.strerror))
    State.tmps.remove(tmp)
    fsync_dir(folder)
    release_lock()

    out('rotated %d log lines to %s' % (n, rotated))
    if not carries:
        err('note.py: no --carry given. Carry forward what is still live: running jobs, agents, '
            'holds, what the user owes. Add them now: note.py add %s "Carried forward: ..."'
            % note)
    return 0


def main(argv):
    if not argv:
        usage()
    State.tmps, State.own_archive, State.kept_archive, State.lock = [], None, None, None
    try:
        max_raw = os.environ.get('NOTE_MAX_LINES') or '300'
        if not WHOLE_RE.match(max_raw):
            die2("NOTE_MAX_LINES must be a whole number, not '%s'" % max_raw)
        max_lines = int(max_raw, 10)
        cmd, rest = argv[0], argv[1:]
        if cmd == 'now':
            if rest:
                usage()
            out(read_stamp())
            return 0
        if cmd == 'add':
            if not rest:
                usage()
            return cmd_add(rest, max_lines)
        if cmd == 'rotate':
            if not rest:
                usage()
            return cmd_rotate(rest)
        if cmd == 'check':
            if len(rest) != 1:
                usage()
            return cmd_check(rest, max_lines)
        if cmd in ('-h', '--help'):
            usage()
        err('note.py: unknown command: %s' % cmd)
        usage()
    except Failure as e:
        err('note.py: ', e.message)
        return e.code
    finally:
        cleanup()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    sys.exit(main(sys.argv[1:]))
