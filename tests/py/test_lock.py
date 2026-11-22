#!/usr/bin/env python3
"""Tests for lock.py that the command line cannot force: two releases by one owner and an
acquire by another, interleaved at the worst moment, and a call that finds the mutex held.
tests/shared-resources.sh runs this file and counts its lines.

  python3 -B tests/py/test_lock.py [path to lock.py]

Each scenario runs in a child process with a deadline the parent enforces, so a regression that
blocks forever is a failed check, not a hung suite. Inside the child, lock.py's main runs in
threads. Each call opens its own file descriptors, so an flock taken in one thread holds the
others off as it would another process.

Prints one "  ok    <name>" or "  FAIL  <name>" line per check.
Exit code: 0 all passed, 1 at least one failed.
"""
import errno
import fcntl
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SCRIPT = os.path.join(ROOT, 'plugins', 'flow', 'skills', 'orchestrate', 'scripts',
                              'lock.py')
DEADLINE_S = 30     # the longest a scenario may run before the parent kills it
STEP_S = 5          # the longest one thread may take to reach the next point

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


def owner_of(path):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith('owner='):
                    return line[len('owner='):].strip()
    except OSError:
        return None
    return ''


# The child side.

def load(script):
    spec = importlib.util.spec_from_file_location('lock', script)
    lock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lock)
    return lock


def interleaved(lock, folder):
    """Release A by alpha pauses after its owner check, in its unlink. Release B by alpha and an
    acquire by beta then run until each is either waiting for the mutex or done. Only then does
    A go on."""
    codes = {}
    reached = {'release B': threading.Event(), 'acquire beta': threading.Event()}
    paused, go = threading.Event(), threading.Event()
    a_timed_out = []
    first = []
    real_unlink, real_flock = os.unlink, fcntl.flock

    def slow_unlink(p, *args, **kwargs):
        if str(p).endswith('db.lock') and not first:
            first.append(p)
            paused.set()
            if not go.wait(STEP_S * 3):
                a_timed_out.append(True)
        return real_unlink(p, *args, **kwargs)

    def watched_flock(fd, op):
        try:
            return real_flock(fd, op)
        except OSError as e:
            # A call that finds the mutex taken has reached the point where it contends.
            name = threading.current_thread().name
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN) and name in reached:
                reached[name].set()
            raise

    def call(argv, key):
        try:
            codes[key] = lock.main(argv)
        except SystemExit as e:
            codes[key] = e.code
        finally:
            if key in reached:
                reached[key].set()     # done counts as having had its turn

    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    call(['acquire', 'db', '--owner', 'alpha', '--dir', folder], 'setup')
    os.unlink = slow_unlink
    fcntl.flock = watched_flock
    a = threading.Thread(target=call, name='release A', daemon=True,
                         args=(['release', 'db', '--owner', 'alpha', '--dir', folder],
                               'release A'))
    a.start()
    a_paused = paused.wait(STEP_S)
    b = threading.Thread(target=call, name='release B', daemon=True,
                         args=(['release', 'db', '--owner', 'alpha', '--dir', folder],
                               'release B'))
    c = threading.Thread(target=call, name='acquire beta', daemon=True,
                         args=(['acquire', 'db', '--owner', 'beta', '--dir', folder],
                               'acquire beta'))
    b.start()
    c.start()
    b_reached = reached['release B'].wait(STEP_S)
    c_reached = reached['acquire beta'].wait(STEP_S)
    go.set()
    for t in (a, b, c):
        t.join(STEP_S * 3)
    stuck = [t.name for t in (a, b, c) if t.is_alive()]
    if stuck:
        # A worker still running may yet change the lock: nothing read now would be a result.
        return {'stuck': stuck}
    return {
        'codes': codes, 'owner': owner_of(os.path.join(folder, 'db.lock')),
        'a_paused': a_paused, 'a_timed_out': bool(a_timed_out),
        'b_reached': b_reached, 'c_reached': c_reached, 'stuck': stuck,
        'mutex_file': os.path.exists(os.path.join(folder, '.db.mutex')),
    }


def busy(lock, folder):
    """The parent holds the mutex. A release and an acquire must give up with exit 2."""
    codes = {}
    sys.stdout = io.StringIO()
    sys.stderr = err = io.StringIO()
    lock.MUTEX_WAIT_S = 0.5
    started = time.monotonic()
    for key, argv in (('release', ['release', 'db', '--owner', 'alpha', '--dir', folder]),
                      ('acquire', ['acquire', 'db', '--owner', 'beta', '--dir', folder])):
        try:
            codes[key] = lock.main(argv)
        except SystemExit as e:
            codes[key] = e.code
    return {'codes': codes, 'took': time.monotonic() - started, 'err': err.getvalue()}


def child(scenario, script, folder, result):
    lock = load(script)
    outcome = (interleaved if scenario == 'interleaved' else busy)(lock, folder)
    with open(result, 'w') as f:
        json.dump(outcome, f)
    # Daemon threads that never stopped must not keep the child alive.
    os._exit(0)


# The parent side.

def run_child(scenario, script, folder, tmp, deadline=DEADLINE_S):
    """Run one scenario in a child process. Returns its result, or None and the reason."""
    result = os.path.join(tmp, scenario + '.json')
    try:
        proc = subprocess.run([sys.executable, '-B', os.path.abspath(__file__), '--child',
                               scenario, script, folder, result],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=deadline)
    except subprocess.TimeoutExpired:
        return None, "the scenario did not finish within %ds and was killed" % deadline
    try:
        with open(result) as f:
            return json.load(f), ''
    except (OSError, ValueError):
        return None, 'no result (exit %d): %s' % (proc.returncode, proc.stdout.decode(
            'utf-8', 'replace'))


def tests(script, tmp):
    folder = os.path.join(tmp, 'race')
    os.mkdir(folder)
    r, why = run_child('interleaved', script, folder, tmp)
    check('the interleaving scenario finished in time', r is not None, why)
    if r is None:
        return
    check('every worker stopped', r['stuck'] == [], r['stuck'])
    if r['stuck']:
        return      # the lock checks below would read a lock a worker may still change
    codes = r['codes']
    check('release A reached its pause after the owner check', r['a_paused'], r)
    check('release B reached the mutex or finished while A was paused', r['b_reached'], r)
    check("beta's acquire reached the mutex or finished while A was paused", r['c_reached'], r)
    check('release A waited at its pause until told to go on', not r['a_timed_out'], r)
    check('a paused release does not remove the lock beta took meanwhile', r['owner'] == 'beta',
          'owner at the end: %r, exit codes: %r' % (r['owner'], codes))
    check('beta was told it holds the lock', codes.get('acquire beta') == 0, codes)
    check('the paused release by alpha exits 0', codes.get('release A') == 0, codes)
    # Release B and beta's acquire both wait for the mutex, in either order. B before beta finds
    # the lock free (0). Beta before B finds beta's lock, which alpha may not release (1).
    check('the second release by alpha finds the lock free or held by beta',
          codes.get('release B') in (0, 1), codes)
    check('the mutex file stays after the calls', r['mutex_file'], sorted(os.listdir(folder)))

    # A held mutex means another lock.py is mid-call. The wait for it is short, then exit 2.
    folder = os.path.join(tmp, 'busy')
    os.mkdir(folder)
    with open(os.path.join(folder, 'db.lock'), 'w') as f:
        f.write('owner=alpha\n')
    fd = os.open(os.path.join(folder, '.db.mutex'), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r, why = run_child("busy", script, folder, tmp, deadline=10)
    finally:
        os.close(fd)
    check('the busy-mutex calls finished in time', r is not None, why)
    if r is None:
        return
    check('a release while the mutex is held exits 2', r['codes'].get('release') == 2, r)
    check('an acquire while the mutex is held exits 2', r['codes'].get('acquire') == 2, r)
    check('the wait for the mutex is short', r['took'] < 5, r['took'])
    check('it says another lock.py is mid-call', 'another lock.py' in r['err'], r['err'])
    check('the lock is untouched', owner_of(os.path.join(folder, 'db.lock')) == 'alpha')


def main(argv):
    if argv[:1] == ['--child']:
        child(*argv[1:5])
    script = os.path.abspath(argv[0]) if argv else DEFAULT_SCRIPT
    tmp = tempfile.mkdtemp()
    try:
        tests(script, tmp)
    finally:
        shutil.rmtree(tmp)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
