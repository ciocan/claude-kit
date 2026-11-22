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

# A stub gh: view prints the body in $GH_STUB/body as JSON, edit stores the body file. Every call
# is logged to $GH_STUB/calls.
STUB = r'''#!/usr/bin/env python3
import json, os, shutil, sys
d = os.environ['GH_STUB']
with open(os.path.join(d, 'calls'), 'a') as f:
    f.write('gh %s\n' % ' '.join(sys.argv[1:]))
args = sys.argv[1:]
if args[:2] == ['issue', 'view']:
    with open(os.path.join(d, 'body'), 'rb') as f:
        print(json.dumps({'body': f.read().decode('utf-8')}))
elif args[:2] == ['issue', 'edit']:
    shutil.copyfile(args[args.index('--body-file') + 1], os.path.join(d, 'body'))
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
    message = tick.interrupted_message('gh issue edit 5 --body-file /b/issue-5.before.md')
    check('a stop during the edit prints the restore command',
          message is not None and message.endswith('\n  gh issue edit 5 --body-file '
                                                   '/b/issue-5.before.md'), message)

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
    check('no backup or lock is left', os.listdir(os.path.join(world, 'backups')) == [],
          os.listdir(os.path.join(world, 'backups')))


if __name__ == '__main__':
    sys.exit(main())
