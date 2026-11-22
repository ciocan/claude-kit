#!/usr/bin/env python3
"""Hold a named lock on a shared resource, across sessions, worktrees and short-lived shells.

Usage:
  lock.py acquire <name> [--owner <label>] [--note <text>] [--wait <seconds>] [--dir <dir>]
  lock.py release <name> [--owner <label>] [--force] [--dir <dir>]
  lock.py status  <name> [--dir <dir>]

The lock is the file <dir>/<name>.lock with the lines owner=, pid=, host=, time=, epoch= and
note=. acquire creates it with O_CREAT | O_EXCL, so exactly one caller wins, and writes it in one
write. It is not a mkdir: where coreutils is the Rust rewrite (uutils 0.10), two mkdir calls on
one path at the same moment can both exit 0. It is not an flock either: the lock must outlive the
process that took it, because an agent takes it in one shell and releases it from another.

Ownership is the label, not a pid: every shell an agent runs is new, so pass the same label each
time. The holder may acquire again. A lock is never broken for its age. The owner releases it, or
a person decides and runs release with --force. A lock file without an owner line counts as held
by "unknown", and only --force releases it: HELD then names no --owner command.

acquire and release each hold a short flock on <dir>/.<name>.mutex while they look at the lock
file and create or remove it. Without it, two releases by one owner and an acquire by another
could interleave: release A passes the owner check and pauses, release B removes the lock, beta
acquires, and A goes on and removes beta's lock, so a third session gets in while beta works.
The mutex is held for a few system calls, never while waiting for the lock. Its file is never
removed: a process that locked a removed file and one that locked its replacement would both
think they hold it. status takes no mutex. When another lock.py holds the mutex for more than a
few seconds, the call gives up with exit 2.

Prints one of ACQUIRED, ALREADY HELD, RELEASED, FORCED release, FREE or HELD (with the owner, the
time, the age, the note and how to release it).

Env: LOCK_OWNER is the label when --owner is absent. LOCK_DIR is the folder (default
$XDG_STATE_HOME/claude-kit/locks, else ~/.local/state/claude-kit/locks). LOCK_POLL_S is the
poll interval for --wait (default 5).

Exit codes: 0 ok, 1 held by someone else or the wait ran out, 2 usage, or another lock.py held
            the mutex too long.
"""
import contextlib
import errno
import fcntl
import os
import re
import shlex
import socket
import sys
import time

NAME_RE = re.compile(r'[A-Za-z0-9._-]+\Z')
POLL_RE = re.compile(r'[0-9]+(?:[.][0-9]+)?\Z')
WAIT_RE = re.compile(r'[0-9]+\Z')
MUTEX_WAIT_S = 5    # how long to wait for another lock.py that is mid-call


def usage():
    sys.stderr.write(__doc__)
    sys.exit(2)


def die(msg):
    sys.stderr.write('lock.py: %s\n' % msg)
    sys.exit(2)


def age(s):
    """Seconds as a short readable age."""
    s = max(s, 0)
    if s < 60:
        return '%ds' % s
    if s < 3600:
        return '%dm' % (s // 60)
    if s < 86400:
        return '%dh %dm' % (s // 3600, s % 3600 // 60)
    return '%dd %dh' % (s // 86400, s % 86400 // 3600)


def read_field(lock, field, default):
    """The first value of field= in the lock file, or default when it is missing or empty."""
    try:
        with open(lock, 'rb') as f:
            data = f.read()
    except OSError:
        return default
    key = field.encode() + b'='
    for line in data.split(b'\n'):
        if line.startswith(key):
            value = line[len(key):]
            return os.fsdecode(value) if value else default
    return default


@contextlib.contextmanager
def name_mutex(folder, name):
    """Hold the flock on <folder>/.<name>.mutex for the length of a with block, or exit 2."""
    path = '%s/.%s.mutex' % (folder, name)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as e:
        die('cannot open %s: %s' % (path, e.strerror))
    try:
        deadline = time.monotonic() + MUTEX_WAIT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    die('cannot lock %s: %s' % (path, e.strerror))
                if time.monotonic() >= deadline:
                    die('another lock.py has held %s for %ss and is mid-call on %s. Nothing was '
                        'changed. Run again in a moment.' % (path, MUTEX_WAIT_S, name))
                time.sleep(0.01)
        yield
    finally:
        # Closing drops the flock. The file stays.
        os.close(fd)


def release_lock(folder, name, lock, owner, force):
    """Under the mutex, check the owner and remove the lock file.

    Returns (outcome, held by, since): outcome is free, released, forced or held. Raises OSError
    when the file cannot be removed.
    """
    with name_mutex(folder, name):
        if not os.path.exists(lock):
            return 'free', None, None
        o = read_field(lock, 'owner', 'unknown')
        t = read_field(lock, 'time', 'unknown')
        if not force and read_field(lock, 'owner', '') != owner:
            return 'held', o, t
        try:
            os.unlink(lock)
        except FileNotFoundError:
            pass
        return ('forced' if force else 'released'), o, t


def lock_text(owner, note):
    """The lock file's content."""
    host = os.environ.get('HOSTNAME') or socket.gethostname() or 'unknown'
    now = time.time()
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))
    text = 'owner=%s\npid=%d\nhost=%s\ntime=%s\nepoch=%d\nnote=%s\n' % (
        owner, os.getppid(), host, stamp, int(now), note)
    return stamp, os.fsencode(text)


def main(argv):
    if len(argv) < 2:
        usage()
    cmd = argv[0]
    if cmd not in ('acquire', 'release', 'status'):
        usage()
    args = argv[1:]

    env = os.environ
    home = env.get('HOME', '')
    state = env.get('XDG_STATE_HOME') or (home + '/.local/state' if home else '')
    folder = env.get('LOCK_DIR') or (state + '/claude-kit/locks' if state else '')
    owner = env.get('LOCK_OWNER', '')
    name = note = wait = ''
    force = False
    dir_arg = ''
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('--owner', '--note', '--wait', '--dir'):
            if i + 1 >= len(args):
                usage()
            value = args[i + 1]
            i += 2
            if a == '--owner':
                owner = value
            elif a == '--note':
                note = value
            elif a == '--wait':
                wait = value
            else:
                folder = value
                dir_arg = ' --dir ' + shlex.quote(value)
        elif a == '--force':
            force = True
            i += 1
        elif a in ('-h', '--help') or a.startswith('--'):
            usage()
        else:
            if name:
                die('unexpected argument: %s' % a)
            name = a
            i += 1

    if not name:
        usage()
    if not NAME_RE.match(name):
        die("bad lock name '%s': use letters, digits, dot, dash, underscore" % name)
    if cmd == 'acquire' and force:
        die('--force belongs to release')
    if cmd == 'release' and (note or wait):
        die('--note and --wait belong to acquire')
    if cmd == 'status' and (note or wait or force):
        die('status takes only a name and --dir')
    if cmd == 'acquire' or (cmd == 'release' and not force):
        if not owner:
            die('an owner label is required: pass --owner <label> or set LOCK_OWNER.\n'
                'Every command runs in a new shell, so a pid cannot show who holds the lock. The '
                'label does,\nso use the same label to acquire and to release.')
    if wait and not WAIT_RE.match(wait):
        die("--wait takes whole seconds, got '%s'" % wait)
    # int() reads 08 as eight. The shell version once read it as a bad octal number, and a free
    # lock then read as held.
    wait_s = int(wait, 10) if wait else None
    poll = env.get('LOCK_POLL_S') or '5'
    if not POLL_RE.match(poll):
        die("LOCK_POLL_S must be a number of seconds, got '%s'" % poll)
    poll_s = float(poll)
    if not folder:
        die('no lock folder: set LOCK_DIR or HOME, or pass --dir')
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        die('cannot create the lock folder %s' % folder)
    lock = folder + '/' + name + '.lock'
    note = note.replace('\n', ' ')
    owner = owner.replace('\n', ' ')

    def held():
        o = read_field(lock, 'owner', 'unknown')
        t = read_field(lock, 'time', 'unknown')
        e = read_field(lock, 'epoch', '')
        n = read_field(lock, 'note', 'none')
        a = 'age unknown'
        if WAIT_RE.match(e):
            a = age(int(time.time()) - int(e))
        print('HELD %s by %s since %s (%s, note: %s)' % (name, o, t, a, n))
        recorded = read_field(lock, 'owner', '')
        if recorded:
            # Quoted, so the line runs as printed whatever the label holds.
            print('  It is never broken for age. The owner releases it: %s release %s --owner %s%s'
                  % (sys.argv[0], name, shlex.quote(recorded), dir_arg))
            print('  or a person decides it is abandoned and runs: %s release %s --force%s'
                  % (sys.argv[0], name, dir_arg))
        else:
            # No owner is recorded, so no label releases it. Only --force does.
            print('  No owner is recorded, so only a person can release it, with: %s release %s '
                  '--force%s' % (sys.argv[0], name, dir_arg))

    def try_acquire():
        """True when taken now or already ours, False when another holds it."""
        with name_mutex(folder, name):
            return create()

    def create():
        for _ in range(3):
            stamp, text = lock_text(owner, note)
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                # Released between the create and this check: try again.
                if not os.path.exists(lock):
                    continue
                if read_field(lock, 'owner', '') == owner:
                    print('ALREADY HELD %s by %s since %s'
                          % (name, owner, read_field(lock, 'time', 'unknown')))
                    return True
                return False
            except OSError as e:
                die('cannot create %s: %s' % (lock, e.strerror))
            try:
                written = os.write(fd, text)
                if written != len(text):
                    raise OSError(0, 'short write')
            except OSError as e:
                os.close(fd)
                os.unlink(lock)
                die('cannot write %s: %s' % (lock, e.strerror))
            os.close(fd)
            print('ACQUIRED %s by %s at %s' % (name, owner, stamp))
            return True
        die('cannot create %s' % lock)

    if cmd == 'acquire':
        deadline = time.time() + (wait_s or 0)
        while True:
            if try_acquire():
                return 0
            if wait_s is None or time.time() >= deadline:
                if wait_s is not None:
                    print('WAITED %ds for %s, still held.' % (wait_s, name))
                held()
                return 1
            time.sleep(poll_s)

    if cmd == 'release':
        try:
            outcome, o, t = release_lock(folder, name, lock, owner, force)
        except OSError:
            sys.stderr.write('could not remove %s\n' % lock)
            return 1
        if outcome == 'free':
            print('FREE %s' % name)
            return 0
        if outcome == 'forced':
            print('FORCED release of %s, was held by %s since %s' % (name, o, t))
            return 0
        if outcome == 'released':
            print('RELEASED %s' % name)
            return 0
        held()
        return 1

    # status
    if os.path.exists(lock):
        held()
        return 1
    print('FREE %s' % name)
    return 0


if __name__ == '__main__':
    # Names and notes come from argv as given, bytes that are not UTF-8 included.
    sys.stdout.reconfigure(errors='surrogateescape')
    sys.exit(main(sys.argv[1:]))
