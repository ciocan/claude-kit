#!/usr/bin/env python3
"""Tests for lock.py that the command line cannot force: two releases by one owner and an
acquire by another, interleaved at the worst moment. tests/shared-resources.sh runs this file and
counts its lines.

  python3 -B tests/py/test_lock.py [path to lock.py]

Runs lock.py's main in threads, with os.unlink made to pause in the first release, after its
owner check. Each call opens its own file descriptors, so an flock taken in one thread holds
the others off as it would another process.
Prints one "  ok    <name>" or "  FAIL  <name>" line per check.
Exit code: 0 all passed, 1 at least one failed.
"""
import fcntl
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = (sys.argv[1] if len(sys.argv) > 1 else
          os.path.join(ROOT, 'plugins', 'flow', 'skills', 'orchestrate', 'scripts', 'lock.py'))
spec = importlib.util.spec_from_file_location('lock', SCRIPT)
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)

FAILED = 0


def check(name, cond, detail=''):
    global FAILED
    if cond:
        print('  ok    %s' % name)
    else:
        FAILED += 1
        print('  FAIL  %s' % name)
        if detail:
            for line in str(detail).splitlines():
                print('        %s' % line)


def call(argv, codes, key):
    """lock.main(argv) in a thread: the exit code lands in codes[key]."""
    try:
        codes[key] = lock.main(argv)
    except SystemExit as e:
        codes[key] = e.code


def quiet(argv):
    saved = sys.stdout
    sys.stdout = io.StringIO()
    try:
        lock.main(argv)
    finally:
        sys.stdout = saved


def owner_of(path):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith('owner='):
                    return line[len('owner='):].strip()
    except OSError:
        return None
    return ''


def interleaved(folder):
    """Release A by alpha pauses after its owner check. Meanwhile release B by alpha and an
    acquire by beta run. Then A goes on. Returns the owner of the lock at the end and the codes."""
    path = os.path.join(folder, 'db.lock')
    quiet(['acquire', 'db', '--owner', 'alpha', '--dir', folder])
    real_unlink = os.unlink
    paused, go = threading.Event(), threading.Event()
    first = []

    def slow_unlink(p, *args, **kwargs):
        if p.endswith('db.lock') and not first:
            first.append(p)
            paused.set()
            go.wait(5)
        return real_unlink(p, *args, **kwargs)

    codes = {}
    os.unlink = slow_unlink
    saved = sys.stdout
    sys.stdout = io.StringIO()
    try:
        a = threading.Thread(target=call, args=(['release', 'db', '--owner', 'alpha', '--dir',
                                                 folder], codes, 'release A'))
        a.start()
        paused.wait(5)
        b = threading.Thread(target=call, args=(['release', 'db', '--owner', 'alpha', '--dir',
                                                 folder], codes, 'release B'))
        b.start()
        b.join(1)       # without a mutex B is done by now; with one it waits for A
        c = threading.Thread(target=call, args=(['acquire', 'db', '--owner', 'beta', '--dir',
                                                 folder], codes, 'acquire beta'))
        c.start()
        c.join(1)
        go.set()
        for t in (a, b, c):
            t.join(10)
    finally:
        os.unlink = real_unlink
        sys.stdout = saved
    return owner_of(path), codes


def main():
    tmp = tempfile.mkdtemp()
    try:
        tests(tmp)
    finally:
        shutil.rmtree(tmp)
    return 1 if FAILED else 0


def tests(tmp):
    folder = os.path.join(tmp, 'race')
    os.mkdir(folder)
    owner, codes = interleaved(folder)
    check("a paused release does not remove the lock beta took meanwhile", owner == 'beta',
          'owner at the end: %r, exit codes: %r' % (owner, codes))
    check('beta was told it holds the lock', codes.get('acquire beta') == 0, codes)
    check('the paused release by alpha exits 0', codes.get('release A') == 0, codes)
    # Release B and beta's acquire both wait for the mutex, in either order. B before beta finds
    # the lock free (0). Beta before B finds beta's lock, which alpha may not release (1).
    check('the second release by alpha finds the lock free or held by beta',
          codes.get('release B') in (0, 1), codes)
    check('the mutex file stays after the calls', os.path.exists(os.path.join(folder, '.db.mutex')),
          sorted(os.listdir(folder)))

    # A held mutex means another lock.py is mid-call. The wait for it is short, then exit 2.
    folder = os.path.join(tmp, 'busy')
    os.mkdir(folder)
    quiet(['acquire', 'db', '--owner', 'alpha', '--dir', folder])
    fd = os.open(os.path.join(folder, '.db.mutex'), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    saved_wait = getattr(lock, 'MUTEX_WAIT_S', None)
    lock.MUTEX_WAIT_S = 0.5
    codes = {}
    started = time.monotonic()
    try:
        call(['release', 'db', '--owner', 'alpha', '--dir', folder], codes, 'release')
        call(['acquire', 'db', '--owner', 'beta', '--dir', folder], codes, 'acquire')
        took = time.monotonic() - started
        err = sys.stderr.getvalue()
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        lock.MUTEX_WAIT_S = saved_wait
        os.close(fd)
    check('a release while the mutex is held exits 2', codes.get('release') == 2, codes)
    check('an acquire while the mutex is held exits 2', codes.get('acquire') == 2, codes)
    check('the wait for the mutex is short', took < 5, took)
    check('it says another lock.py is mid-call', 'another lock.py' in err, err)
    check('the lock is untouched', owner_of(os.path.join(folder, 'db.lock')) == 'alpha')


if __name__ == '__main__':
    sys.exit(main())
