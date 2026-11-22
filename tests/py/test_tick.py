#!/usr/bin/env python3
"""Tests for the guards in tick.py that no outside fault can reach: the box pattern, the fences,
the edit, and the check that the edited body differs from the original only in the bracket
character of the selected lines. tests/tick.sh runs this file and counts its lines.

  python3 -B tests/py/test_tick.py

Runs tick.py's main against a stub `gh` of its own, put first on PATH. GitHub is never called.
Prints one "  ok    <name>" or "  FAIL  <name>" line per check.
Exit code: 0 all passed, 1 at least one failed.
"""
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'plugins', 'flow', 'skills', 'ship-pr', 'scripts', 'tick.py')
spec = importlib.util.spec_from_file_location('tick', SCRIPT)
tick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tick)

FAILED = 0
B1 = (b'## Tasks\n- [ ] write the parser\n- [x] read the spec\n- [ ] write the tests\n'
      b'- [ ] ship the parser docs\nText with [ ] brackets that is not a box.\n')

# A stub gh: view prints the body in $GH_STUB/body as JSON, edit stores the body it is given, from
# a file or from stdin with --body-file -. Every call is logged to $GH_STUB/calls.
STUB = r'''#!/usr/bin/env python3
import json, os, shutil, sys
d = os.environ['GH_STUB']
with open(os.path.join(d, 'calls'), 'a') as f:
    f.write('gh %s\n' % ' '.join(sys.argv[1:]))
args = sys.argv[1:]
if args[:2] == ['issue', 'view']:
    with open(os.path.join(d, 'body'), 'rb') as f:
        print(json.dumps({'body': f.read().decode('utf-8'),
                          'url': 'https://github.com/o/r/issues/%s' % args[2]}))
elif args[:2] == ['issue', 'edit']:
    source = args[args.index('--body-file') + 1]
    if source == '-':
        data = sys.stdin.buffer.read()
    else:
        with open(source, 'rb') as f:
            data = f.read()
    with open(os.path.join(d, 'body'), 'wb') as f:
        f.write(data)
else:
    sys.exit(9)
'''


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
    """tick.main(argv) with stdout and stderr captured: (exit code, stdout, stderr)."""
    saved = sys.stdout, sys.stderr
    sys.stdout = io.TextIOWrapper(io.BytesIO())
    sys.stderr = io.TextIOWrapper(io.BytesIO())
    try:
        try:
            code = tick.main(argv)
        except SystemExit as e:
            code = e.code
        except Exception as e:      # a traceback the script let out is a failed check
            code = 'raised %s: %s' % (type(e).__name__, e)
        sys.stdout.flush()
        sys.stderr.flush()
        return code, sys.stdout.buffer.getvalue(), sys.stderr.buffer.getvalue()
    finally:
        sys.stdout, sys.stderr = saved


def guard(before, after, selected, want=b'x'):
    return tick.check_edit(before, after, selected, want)


def main():
    tmp = tempfile.mkdtemp()
    try:
        tests(tmp)
    finally:
        shutil.rmtree(tmp)
    return 1 if FAILED else 0


def tests(tmp):
    # The box pattern and the fences.
    lines = tick.split_lines(b'## Plan\n- [ ] real one\n```md\n- [ ] template\n```\n1. [ ] ordered\n'
                             b'2) [X] bracket\n> - [ ] quoted\n~~~\n* [ ] tmpl\n~~~\n\t+ [x] tab\n'
                             b'-[ ] no\n- [] no\n- [ ]no space after\n')
    states = tick.box_states(lines)
    check('boxes are found outside fences only',
          states == [None, b' ', None, None, None, b' ', b'X', b' ', None, None, None, b'x',
                     None, None, None], states)
    check('a CRLF line is a box', tick.box_states([b'- [ ] one\r']) == [b' '])
    check('a quote with space before the marker is a box',
          tick.box_states([b'>  > * [ ] deep']) == [b' '])

    # Fences and comments by CommonMark's rules, as the page shows them.
    def states_of(text):
        return tick.box_states(tick.split_lines(text))

    cases = [
        ('a ``` line inside a ```` fence does not close it',
         b'- [x] real\n````md\n```\n- [ ] template\n```\n````\n- [ ] after\n',
         [b'x', None, None, None, None, None, b' ']),
        ('a ~~~ line inside a ``` fence does not close it',
         b'```\n~~~\n- [ ] template\n```\n- [ ] after\n', [None, None, None, None, b' ']),
        ('a closing fence with text after it does not close',
         b'```\n``` x\n- [ ] code\n```\n- [ ] out\n', [None, None, None, None, b' ']),
        ('a backtick in the info string means no fence',
         b'```npm install``` first\n- [ ] after\n', [None, b' ']),
        ('a tilde fence may hold backticks in its info string',
         b'~~~ `x`\n- [ ] code\n~~~\n- [ ] out\n', [None, None, None, b' ']),
        ('an unclosed fence runs to the end', b'- [ ] a\n```\n- [ ] code\n', [b' ', None, None]),
        ('a fence indented three spaces opens', b'   ```\n- [ ] code\n```\n', [None, None, None]),
        ('a fence indented four spaces at the top does not open',
         b'text\n\n    ```\n- [ ] a\n', [None, None, None, b' ']),
        ('a fence inside a list item may be indented past the item',
         b'- [ ] step\n    ```\n    - [ ] code\n    ```\n- [ ] next\n',
         [b' ', None, None, None, b' ']),
        ('a fence in a quote ends with the quote', b'> ```\n> - [ ] code\n- [ ] out\n',
         [None, None, b' ']),
        ('a quoted ``` line does not close a fence outside the quote',
         b'```\n> ```\n- [ ] code\n```\n- [ ] out\n', [None, None, None, None, b' ']),
        ('fences with CRLF line ends', b'```\r\n- [ ] code\r\n```\r\n- [ ] out\r\n',
         [None, None, None, b' ']),
        ('a box in a multi-line comment is hidden',
         b'<!--\n- [ ] hidden\n-->\n- [ ] shown\n', [None, None, None, b' ']),
        ('a one-line comment hides its line only',
         b'<!-- - [ ] hidden -->\n- [ ] shown\n', [None, b' ']),
        ('a comment opened inside a fence is code', b'```\n<!--\n```\n- [ ] out\n',
         [None, None, None, b' ']),
        ('a fence opened inside a comment is not one', b'<!--\n```\n-->\n- [ ] out\n',
         [None, None, None, b' ']),
        ('one to four spaces after the marker', b'-  [ ] two\n1.    [ ] four\n-     [ ] five\n',
         [b' ', b' ', None]),
    ]
    for name, text, want in cases:
        got = states_of(text)
        check(name, got == want, got)

    # The guard uses the same definition: a box line in a fence is not a box to change.
    fenced = b'- [ ] real\n```\n- [ ] template\n```\n'
    bad, refusal = guard(fenced, fenced.replace(b'- [ ] template', b'- [x] template'), [3])
    check('the guard refuses a change to a box line inside a fence',
          bad == ['BAD line 3: not a checkbox line'], (bad, refusal))
    spaced = b'-  [ ] two\n'
    check('the guard takes a two-space marker',
          guard(spaced, tick.build_edit(spaced, [1], b'x'), [1]) == ([], None))

    # What a stop by INT or TERM prints: the restore command once the edit call has started.
    check('a stop before the edit prints nothing', tick.interrupted_message(None) is None)
    message = tick.interrupted_message(tick.restore_lines('5', 'github.com/o/r',
                                                          '/b/issue-5.before.md'))
    check('a stop during the edit prints the restore command',
          message is not None and message.endswith(
              '\n  gh issue edit 5 --repo github.com/o/r --body-file /b/issue-5.before.md'),
          message)

    # The restore command names the issue's repository, read from its url.
    for url, want in (
            ('https://github.com/o/r/issues/5', 'github.com/o/r'),
            ('https://GitHub.com/o/r/issues/5/', 'github.com/o/r'),
            ('https://ghe.example.com/team/app/issues/5', 'ghe.example.com/team/app'),
            ('https://ghe.example.com:8443/team/app/issues/5', 'ghe.example.com:8443/team/app'),
            ('https://github.com/o/r/pull/5', 'github.com/o/r'),
            ('https://github.com/o/r/issues/6', None),
            ('https://github.com/o/r', None),
            ('file:///o/r/issues/5', None),
            ('https://github.com/o/r b/issues/5', None),
            ('', None),
            (None, None)):
        got = tick.repo_from_url(url, '5')
        check('the repository from %r is %r' % (url, want), got == want, got)
    # Without a repository no runnable command is printed, only its shape with a placeholder.
    unknown = tick.restore_lines('5', None, '/b/x.before.md')
    lines = unknown.split('\n')
    check('without a repository it says the repository is unknown and names the backup',
          lines[0].startswith('The repository of #5 is unknown') and '/b/x.before.md' in lines[0],
          unknown)
    check('without a repository the last line is the shape with a placeholder',
          lines[-1] == '  gh issue edit 5 --repo (REPOSITORY) --body-file /b/x.before.md', unknown)
    hostless = tick.restore_lines('5', 'o/r', '/b/x.before.md').split('\n')
    check('a repository without a host gives the shape with a host placeholder',
          hostless[0].startswith('The host of #5 is unknown')
          and hostless[-1] == '  gh issue edit 5 --repo (HOST)/o/r --body-file /b/x.before.md',
          hostless)
    check('a repository that names its host gives the command',
          tick.restore_lines('5', 'ghe.example.invalid/o/r', '/b/x.before.md')
          == '  gh issue edit 5 --repo ghe.example.invalid/o/r --body-file /b/x.before.md')
    check('without a repository no gh issue edit line lacks the placeholder',
          all('(REPOSITORY)' in line for line in lines if line.startswith('  gh issue edit')),
          unknown)
    sh = shutil.which('sh')
    if sh:
        probe = subprocess.run([sh, '-n', '-c', lines[-1]], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        check('sh refuses the shape as it stands', probe.returncode != 0, probe.returncode)
    check('a restore command quotes its parts',
          tick.restore_lines('5', 'github.com/o/r', '/b/a b.before.md')
          == "  gh issue edit 5 --repo github.com/o/r --body-file '/b/a b.before.md'")

    # On a read-back that differs, compare first, restore last.
    message = tick.mismatch_message('5', ['--- sent'], '/b/x.before.md', '/b/x.after.md',
                                    '/b/x.readback.md',
                                    tick.restore_lines('5', 'github.com/o/r', '/b/x.before.md'))
    lines = message.split('\n')
    compare = [i for i, line in enumerate(lines) if line.startswith('Compare the read-back')]
    last = [i for i, line in enumerate(lines) if line.startswith('Last resort')]
    command = [i for i, line in enumerate(lines) if line.startswith('  gh issue edit')]
    check('the mismatch message compares before it restores',
          len(compare) == len(last) == len(command) == 1 and compare[0] < last[0] < command[0]
          and command[0] == len(lines) - 1, message)
    check('the mismatch message names the three files', all(
        p in message for p in ('/b/x.before.md', '/b/x.after.md', '/b/x.readback.md')), message)

    # The edit keeps every byte but the bracket character.
    crlf = b'## Tasks\r\n- [ ] one\r\n- [X] two\r\n'
    check('an edit keeps CRLF line ends',
          tick.build_edit(crlf, [2], b'x') == b'## Tasks\r\n- [x] one\r\n- [X] two\r\n')
    check('an edit keeps a missing final newline',
          tick.build_edit(b'- [ ] one\n- [ ] two', [2], b'x') == b'- [ ] one\n- [x] two')

    # The guard. These replace a test that put an awk on PATH that cut the last line off the
    # edited body.
    good = tick.build_edit(B1, [2, 4], b'x')
    check('the guard passes a clean edit', guard(B1, good, [2, 4]) == ([], None))
    shortened = b'\n'.join(good.split(b'\n')[:-2]) + b'\n'
    check('the guard refuses a shortened body',
          guard(B1, shortened, [2, 4]) == ([], 'the edited body has 5 lines, the original 6'),
          guard(B1, shortened, [2, 4]))
    check('the guard refuses an empty body',
          guard(B1, b'', [2]) == ([], 'the edited body is empty'))
    check('the guard refuses a body one byte longer',
          guard(B1, good.replace(b'spec', b'specs'), [2, 4])[1]
          == 'the edited body has %d bytes, the original %d' % (len(B1) + 1, len(B1)))
    bad, refusal = guard(B1, good.replace(b'not a box', b'not a bot'), [2, 4])
    check('the guard refuses a change outside a box line',
          bad == ['BAD line 6: not a checkbox line']
          and refusal == 'the edited body changes more than the selected boxes', (bad, refusal))
    bad, refusal = guard(B1, good.replace(b'write the tests', b'write the tesTs'), [2, 4])
    check('the guard refuses more than the bracket changed on a box line',
          bad == ['BAD line 4: more than the bracket character changed'], (bad, refusal))
    bad, refusal = guard(B1, B1.replace(b'- [x] read', b'- [X] read'), [3])
    check('the guard refuses a tick of a box already ticked',
          bad == ['BAD line 3: [x] became [X]'], (bad, refusal))
    bad, refusal = guard(B1, B1.replace(b'- [ ] write the parser', b'- [x] write the parser'),
                         [2], want=b' ')
    check('the guard refuses the wrong direction',
          bad == ['BAD line 2: [ ] became [x]'], (bad, refusal))
    check('the guard refuses a change to a box that was not selected',
          guard(B1, good, [2]) == ([], 'the edited body changes lines 2 4, the selection is lines 2'))
    check('the guard refuses an edit that changes nothing',
          guard(B1, B1, [2]) == ([], 'the edited body changes lines none, the selection is lines 2'))

    # Files are created new, never written through a symlink or over a file already there.
    files = os.path.join(tmp, 'files')
    os.mkdir(files, 0o700)
    victim = os.path.join(files, 'victim')
    with open(victim, 'wb') as f:
        f.write(b'a file of the user\n')
    link = os.path.join(files, 'issue-5.after.md')
    os.symlink(victim, link)
    tick.Run.files = []
    files_fd = os.open(files, os.O_RDONLY | os.O_DIRECTORY)
    try:
        tick.write_new(files_fd, 'issue-5.after.md', b'body')
        check('write_new refuses a symlink at the name', False, 'it wrote')
    except tick.Collision:
        check('write_new refuses a symlink at the name', True)
    with open(victim, 'rb') as f:
        check("the symlink's target is unchanged", f.read() == b'a file of the user\n')
    check('the symlink stays a symlink', os.path.islink(link))
    check('a refused name is not marked for cleanup', tick.Run.files == [], tick.Run.files)
    try:
        tick.write_new(files_fd, 'victim', b'body')
        check('write_new refuses a file already at the name', False, 'it wrote')
    except tick.Collision:
        check('write_new refuses a file already at the name', True)
    fresh_path = os.path.join(files, 'new.after.md')
    tick.write_new(files_fd, 'new.after.md', b'body')
    check('write_new creates a new file with mode 600',
          os.stat(fresh_path).st_mode & 0o777 == 0o600, oct(os.stat(fresh_path).st_mode))
    os.close(files_fd)
    tick.Run.files = []

    # Folders another user could write in are refused.
    for mode, refused in ((0o777, True), (0o770, True), (0o757, True), (0o755, False),
                          (0o700, False)):
        folder = os.path.join(tmp, 'dir%o' % mode)
        os.mkdir(folder)
        os.chmod(folder, mode)
        try:
            tick.open_private_dir(folder, 'backup folder')
            got = False
        except tick.Stop:
            got = True
        check('a folder with mode %o is %s' % (mode, 'refused' if refused else 'accepted'),
              got == refused)
    link_dir = os.path.join(tmp, 'linked')
    os.symlink(os.path.join(tmp, 'dir700'), link_dir)
    try:
        tick.open_private_dir(link_dir, 'backup folder')
        check('a folder given as a symlink is refused', False)
    except tick.Stop as e:
        check('a folder given as a symlink is refused', 'is a symlink' in e.message, e.message)
    for fd in tick.Run.folders:
        os.close(fd)
    tick.Run.folders = []

    wired(tmp)


def wired(tmp):
    """Runs of tick.py's main against the stub gh."""
    # The guard is wired in: with an edit builder that drops the last line, tick.py refuses and
    # gh never gets an edit call.
    stub_dir = os.path.join(tmp, 'bin')
    os.mkdir(stub_dir)
    with open(os.path.join(stub_dir, 'gh'), 'w') as f:
        f.write(STUB)
    os.chmod(os.path.join(stub_dir, 'gh'), 0o755)
    world = os.path.join(tmp, 'world')
    os.mkdir(world)
    with open(os.path.join(world, 'body'), 'wb') as f:
        f.write(B1)
    saved_env = dict(os.environ)
    os.environ['PATH'] = stub_dir + os.pathsep + os.environ.get('PATH', '')
    os.environ['GH_STUB'] = world
    os.environ['TICK_BACKUP_DIR'] = os.path.join(world, 'backups')
    os.environ['TICK_LOCK_DIR'] = os.path.join(world, 'locks')
    real_build = tick.build_edit

    def build_short(body, selected, want):
        edited = real_build(body, selected, want)
        return b'\n'.join(edited.split(b'\n')[:-2]) + b'\n'

    tick.build_edit = build_short
    try:
        code, out, err = run(['5', '--all'])
    finally:
        tick.build_edit = real_build
        os.environ.clear()
        os.environ.update(saved_env)
    with open(os.path.join(world, 'calls')) as f:
        calls = f.read()
    with open(os.path.join(world, 'body'), 'rb') as f:
        body = f.read()
    check('a shortened edited body is refused', code == 1, (code, err))
    check('the line guard names it', b'the edited body has 5 lines, the original 6' in err, err)
    check('no edit call', 'issue edit' not in calls, calls)
    check('the body is unchanged', body == B1)
    left = (os.listdir(os.path.join(world, 'backups')), os.listdir(os.path.join(world, 'locks')))
    check('no backup or lock is left', left == ([], []), left)

    # gh vanishes after the last read: the edit cannot start, so nothing was sent. That is a
    # refusal before the edit, with a clear line and the same cleanup, not a traceback.
    open(os.path.join(world, 'calls'), 'w').close()
    real_popen = subprocess.Popen

    def gone_at_edit(args, *rest, **kwargs):
        if args[:3] == ['gh', 'issue', 'edit']:
            raise FileNotFoundError(2, 'No such file or directory', 'gh')
        return real_popen(args, *rest, **kwargs)

    os.environ['PATH'] = stub_dir + os.pathsep + os.environ.get('PATH', '')
    os.environ['GH_STUB'] = world
    os.environ['TICK_BACKUP_DIR'] = os.path.join(world, 'backups')
    os.environ['TICK_LOCK_DIR'] = os.path.join(world, 'locks')
    subprocess.Popen = gone_at_edit
    try:
        code, out, err = run(['5', '--all'])
    finally:
        subprocess.Popen = real_popen
        os.environ.clear()
        os.environ.update(saved_env)
    with open(os.path.join(world, 'body'), 'rb') as f:
        body = f.read()
    check('a gh that cannot start for the edit is a refusal', code == 1, (code, err))
    check('it says nothing was sent', b'cannot start gh for the edit' in err
          and b'so nothing was sent' in err, err)
    check('it prints no restore command', b'gh issue edit' not in err, err)
    check('the body is unchanged when gh cannot start', body == B1)
    left = (os.listdir(os.path.join(world, 'backups')), os.listdir(os.path.join(world, 'locks')))
    check('no backup or lock is left when gh cannot start', left == ([], []), left)

    # gh has started, then writing the body to its stdin fails. The edit may have gone out, so
    # this is not "nothing was sent": exit 3, the files kept, the restore block printed.
    open(os.path.join(world, 'calls'), 'w').close()

    class BrokenStdin(real_popen):
        def communicate(self, input=None, timeout=None):
            if list(self.args[:3]) == ['gh', 'issue', 'edit']:
                raise BrokenPipeError(32, 'Broken pipe')
            return real_popen.communicate(self, input, timeout)

    os.environ['PATH'] = stub_dir + os.pathsep + os.environ.get('PATH', '')
    os.environ['GH_STUB'] = world
    os.environ['TICK_BACKUP_DIR'] = os.path.join(world, 'backups')
    os.environ['TICK_LOCK_DIR'] = os.path.join(world, 'locks')
    subprocess.Popen = BrokenStdin
    try:
        code, out, err = run(['5', '--all'])
    finally:
        subprocess.Popen = real_popen
        os.environ.clear()
        os.environ.update(saved_env)
    kept = sorted(os.listdir(os.path.join(world, 'backups')))
    check('a failure after gh started exits 3', code == 3, (code, err))
    check('it does not say nothing was sent', b'nothing was sent' not in err, err)
    check('it says the edit may have landed', b'the edit may have landed' in err, err)
    check('the before and after files are kept',
          [n.rsplit('.', 2)[-2] for n in kept] == ['after', 'before'], kept)
    check('it prints the restore block', err.rstrip(b'\n').split(b'\n')[-1].startswith(
        b'  gh issue edit 5 --repo github.com/o/r --body-file '), err)
    check('no lock is left after a failure once gh started',
          os.listdir(os.path.join(world, 'locks')) == [], os.listdir(os.path.join(world, 'locks')))
    for name in kept:
        os.unlink(os.path.join(world, 'backups', name))

    # The backup folder is renamed away and replaced after the check, just before the edit, by
    # someone who can write in its parent. The new folder holds their .after.md. gh must still get
    # the body tick.py built, and the planted folder must be left as it was.
    with open(os.path.join(world, 'body'), 'wb') as f:
        f.write(B1)
    open(os.path.join(world, 'calls'), 'w').close()
    backups = os.path.join(world, 'swapped')
    planted = b'- [x] planted by someone else\n'
    swapped = []

    def swap_then_run(args, *rest, **kwargs):
        if args[:3] == ['gh', 'issue', 'edit'] and not swapped:
            os.rename(backups, backups + '.moved')
            os.mkdir(backups, 0o700)
            for name in os.listdir(backups + '.moved'):
                if name.endswith('.before.md'):
                    after = name[:-len('.before.md')] + '.after.md'
                    with open(os.path.join(backups, after), 'wb') as f:
                        f.write(planted)
                    swapped.append(after)
        return real_popen(args, *rest, **kwargs)

    os.environ['PATH'] = stub_dir + os.pathsep + os.environ.get('PATH', '')
    os.environ['GH_STUB'] = world
    os.environ['TICK_BACKUP_DIR'] = backups
    os.environ['TICK_LOCK_DIR'] = os.path.join(world, 'locks')
    subprocess.Popen = swap_then_run
    try:
        code, out, err = run(['5', '--all'])
    finally:
        subprocess.Popen = real_popen
        os.environ.clear()
        os.environ.update(saved_env)
    with open(os.path.join(world, 'body'), 'rb') as f:
        body = f.read()
    check('the folder was swapped before the edit', len(swapped) == 1, os.listdir(world))
    check('gh gets the body tick.py built, not the planted one',
          body == real_build(B1, [2, 4, 5], b'x'), body)
    check('the run with a swapped folder succeeds', code == 0, (code, err))
    left = sorted(os.listdir(backups))
    check('the folder put in its place is left as it was', left == swapped, left)
    if swapped:
        with open(os.path.join(backups, swapped[0]), 'rb') as f:
            check('the planted .after.md is untouched', f.read() == planted)
    moved = sorted(os.listdir(backups + '.moved'))
    check('the backup stays in the folder that was checked',
          len(moved) == 1 and moved[0].endswith('.before.md'), moved)


if __name__ == '__main__':
    sys.exit(main())
