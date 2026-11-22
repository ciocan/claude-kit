#!/usr/bin/env python3
"""Tests for the guards in note.py that no outside fault can reach: the clock, the entry, the new
note on rotate, and what a failure or a TERM leaves behind. tests/notes.sh runs this file and
counts its lines.

  python3 -B tests/py/test_note.py

Prints one "  ok    <name>" or "  FAIL  <name>" line per check.
Exit code: 0 all passed, 1 at least one failed.
"""
import importlib.util
import io
import os
import shutil
import signal
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'plugins', 'flow', 'skills', 'long-haul', 'scripts', 'note.py')
spec = importlib.util.spec_from_file_location('note', SCRIPT)
note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(note)

FAILED = 0
NOTE_TEXT = (b'---\nname: goal-demo\n---\n\nSTATUS: RUNNING\n\n'
             b'## 2026-11-20 08:00 UTC\n- Landed: #2\n\n## 2026-11-20 09:30 UTC\n- Running: x\n')
TOP = b'---\nname: goal-demo\n---\n\nSTATUS: RUNNING\n\n'
LOG = NOTE_TEXT[len(TOP):]


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


def run(argv):
    """note.main(argv) with stdout and stderr captured: (exit code, stdout, stderr)."""
    saved = sys.stdout, sys.stderr
    sys.stdout = io.TextIOWrapper(io.BytesIO())
    sys.stderr = io.TextIOWrapper(io.BytesIO())
    try:
        try:
            code = note.main(argv)
        except SystemExit as e:
            code = e.code
        sys.stdout.flush()
        sys.stderr.flush()
        return code, sys.stdout.buffer.getvalue(), sys.stderr.buffer.getvalue()
    finally:
        sys.stdout, sys.stderr = saved


class Patch:
    """Replace attributes for the length of a with block."""

    def __init__(self, obj, **attrs):
        self.obj, self.attrs, self.saved = obj, attrs, {}

    def __enter__(self):
        for k, v in self.attrs.items():
            self.saved[k] = getattr(self.obj, k)
            setattr(self.obj, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(self.obj, k, v)


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def fresh(folder, name='goal.md', text=NOTE_TEXT):
    path = os.path.join(folder, name)
    with open(path, 'wb') as f:
        f.write(text)
    return path


def dotfiles(folder):
    return sorted(n for n in os.listdir(folder) if n.startswith('.'))


def main():
    tmp = tempfile.mkdtemp()
    signal.signal(signal.SIGTERM, note.on_signal)
    os.environ.pop('NOTE_NOW', None)
    os.environ.pop('NOTE_MAX_LINES', None)
    try:
        tests(tmp)
    finally:
        shutil.rmtree(tmp)
    return 1 if FAILED else 0


def tests(tmp):
    # The clock. These replace a test that put a failing `date` on PATH.
    def broken_clock():
        raise OSError('no clock')

    with Patch(note, utc_stamp=broken_clock):
        try:
            note.read_stamp()
            check('a clock that fails gives no stamp', False, 'read_stamp returned')
        except note.Failure as e:
            check('a clock that fails gives no stamp', e.code == 1 and 'no valid time' in e.message,
                  e.message)
        d = tempfile.mkdtemp(dir=tmp)
        path = fresh(d, text=b'top block\n')
        code, _, err = run(['add', path, 'x'])
        check('a clock that fails stops add', code == 1, (code, err))
        check('add with a failed clock wrote nothing', read(path) == b'top block\n', read(path))
        check('add with a failed clock leaves no lock file', dotfiles(d) == [], dotfiles(d))
        code, _, err = run(['rotate', path, '--summary', 's'])
        check('a clock that fails stops rotate', code == 1, (code, err))

    with Patch(note, utc_stamp=lambda: '2026-11-22 10:00 UTC'):
        check('a clock stamp passes', note.read_stamp() == '2026-11-22 10:00 UTC')
    for bad in ('2026-11-22 10:00', '2026-11-22T10:00 UTC', '2026-11-22 10:00 UTC x', 'now'):
        with Patch(note, utc_stamp=lambda: bad):
            try:
                note.read_stamp()
                check('a malformed stamp is refused: %r' % bad, False)
            except note.Failure:
                check('a malformed stamp is refused: %r' % bad, True)

    # Finding b: the stamp is read once the lock is held. The clock moves on while add waits for
    # the lock, the way it does when another writer holds it across a minute boundary.
    real_take = note.take_lock
    moment = {'locked': False}

    def take(path, wait):
        real_take(path, wait)
        moment['locked'] = True

    def clock():
        return '2026-11-22 10:01 UTC' if moment['locked'] else '2026-11-22 10:00 UTC'

    with Patch(note, take_lock=take, utc_stamp=clock):
        d = tempfile.mkdtemp(dir=tmp)
        path = fresh(d)
        code, out, err = run(['add', path, 'late'])
        check('add stamps with the time after the lock is held', code == 0
              and read(path).endswith(b'\n## 2026-11-22 10:01 UTC\n- late\n'), (code, err, read(path)))
        moment['locked'] = False
        code, out, err = run(['rotate', path, '--summary', 's', '--carry', 'c'])
        check('rotate stamps with the time after the lock is held', code == 0
              and b'\n## 2026-11-22 10:01 UTC\n- Rotated:' in b'\n' + read(path),
              (code, err, read(path)))

    # The entry add appends.
    check('an entry after a final newline starts with one blank line',
          note.entry_bytes('2026-11-22 10:00 UTC', [b'- a'], 5, b'\n')
          == b'\n## 2026-11-22 10:00 UTC\n- a\n')
    check('an entry after a last line without a newline ends that line first',
          note.entry_bytes('2026-11-22 10:00 UTC', [b'- a', b'- b'], 5, b'x')
          == b'\n\n## 2026-11-22 10:00 UTC\n- a\n- b\n')
    check('an entry in an empty note starts with one blank line',
          note.entry_bytes('2026-11-22 10:00 UTC', [b'- a'], 0, b'')
          == b'\n## 2026-11-22 10:00 UTC\n- a\n')

    # Finding d: the new note is exactly the top block and the new entry.
    entry = [b'## 2026-11-22 10:00 UTC', b'- Rotated: 5 log lines up to here moved to x.md']
    good = TOP + b'## 2026-11-22 10:00 UTC\n- Rotated: 5 log lines up to here moved to x.md\n'
    check('the new-note guard takes the exact bytes', note.new_note_matches(good, TOP, entry))
    check('the new-note guard refuses a short file', not note.new_note_matches(good[:-1], TOP, entry))
    check('the new-note guard refuses an empty file', not note.new_note_matches(b'', TOP, entry))
    check('the new-note guard refuses an extra byte',
          not note.new_note_matches(good + b'\n', TOP, entry))
    check('the new-note guard refuses a changed top block',
          not note.new_note_matches(good.replace(b'RUNNING', b'RUNNINg'), TOP, entry))

    os.environ['NOTE_NOW'] = '2026-11-22 12:00 UTC'
    try:
        rotate_failures(tmp)
    finally:
        os.environ.pop('NOTE_NOW', None)


def rotate_failures(tmp):
    archive_text = b'# goal log, rotated 2026-11-22 12:00 UTC\n\n' + LOG

    # Finding d, wired in: the temp file comes out one byte short, the way a full disk would leave
    # it. rotate must see it and keep the note.
    real_write_temp = note.write_temp

    def short_write(folder, file, mode, data):
        return real_write_temp(folder, file, mode, data[:-1])

    d = tempfile.mkdtemp(dir=tmp)
    path = fresh(d)
    with Patch(note, write_temp=short_write):
        code, _, err = run(['rotate', path, '--summary', 's'])
    check('a short new note stops rotate', code == 1, (code, err))
    check('it says what was wrong', b'not the top block followed by the new entry' in err, err)
    check('the note is unchanged after a short new note', read(path) == NOTE_TEXT)
    check('no temp file or lock is left after a short new note', dotfiles(d) == [], dotfiles(d))

    # Finding e: once the archive is complete it stays, whatever happens to the note.
    archive = os.path.join(d, 'goal-log-2026-11-22.md')
    check('the verified archive is kept when the new note fails',
          os.path.exists(archive) and read(archive) == archive_text)
    check('the message says where the log also is', b'Its log is also in %s' % archive.encode() in err,
          err)

    def failing_replace(src, dst):
        raise OSError(5, 'Input/output error')

    d = tempfile.mkdtemp(dir=tmp)
    path = fresh(d)
    with Patch(note.os, replace=failing_replace):
        code, _, err = run(['rotate', path, '--summary', 's'])
    archive = os.path.join(d, 'goal-log-2026-11-22.md')
    check('a rename that fails stops rotate', code == 1, (code, err))
    check('the note is unchanged after a failed rename', read(path) == NOTE_TEXT)
    check('the archive is kept and complete after a failed rename',
          os.path.exists(archive) and read(archive) == archive_text)
    check('no temp file or lock is left after a failed rename', dotfiles(d) == [], dotfiles(d))

    # A TERM after the archive is verified: the old script still held the archive as its own
    # until the move, and its cleanup deleted it.
    def term_then_write(folder, file, mode, data):
        os.kill(os.getpid(), signal.SIGTERM)
        return real_write_temp(folder, file, mode, data)

    d = tempfile.mkdtemp(dir=tmp)
    path = fresh(d)
    with Patch(note, write_temp=term_then_write):
        code, _, err = run(['rotate', path, '--summary', 's'])
    archive = os.path.join(d, 'goal-log-2026-11-22.md')
    check('a TERM during rotate exits 130', code == 130, (code, err))
    check('the note is unchanged after a TERM', read(path) == NOTE_TEXT)
    check('the archive survives a TERM once it is complete',
          os.path.exists(archive) and read(archive) == archive_text)
    check('no temp file or lock is left after a TERM', dotfiles(d) == [], dotfiles(d))

    # A TERM while the archive is being written: a half archive is removed.
    real_write_all = note.write_all

    def term_then_write_all(fd, data):
        os.kill(os.getpid(), signal.SIGTERM)
        real_write_all(fd, data)

    d = tempfile.mkdtemp(dir=tmp)
    path = fresh(d)
    with Patch(note, write_all=term_then_write_all):
        code, _, err = run(['rotate', path, '--summary', 's'])
    check('a TERM while the archive is written exits 130', code == 130, (code, err))
    check('a half-written archive is removed', os.listdir(d) == ['goal.md'], os.listdir(d))
    check('the note is unchanged after that TERM', read(path) == NOTE_TEXT)


if __name__ == '__main__':
    sys.exit(main())
