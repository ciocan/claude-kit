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
  --repo <owner/repo>    passed to every gh call. Default: gh's own (the current repository).
                         -R is accepted as well, since that is what gh calls it
  --dry-run              show the lines that would change, edit nothing
  --backup-dir <dir>     where the body is saved before the edit

A box is a list item with [ ], [x] or [X]: a bullet (-, *, +) or an ordered marker (1. or 1)),
then one to four spaces, indented or inside a quote (> ). Lines inside a code fence (``` or ~~~,
by CommonMark's rules) or an HTML comment (<!-- ... -->) are never boxes: the page does not show
them as boxes, so template text is left alone and --line counts what the page shows. A box in a
code block made by indentation alone is still counted.

The body comes from `gh issue view <n> --json body,url` and is parsed from the JSON, so it is the
body as stored, byte for byte. The shell version read it with `gh -q .body`, which prints the
body and then a newline of its own, and had to drop that byte, or every edit would have added a
line end to the issue. The body is handled as bytes: CRLF line ends, a missing final newline and
every other byte survive.

Saves the body as <backup-dir>/issue-<n>-<yyyymmddThhmmssZ>.before.md (-2, -3 when taken) and
edits only when the edited body has the same lines and bytes and differs in nothing but the
bracket character of the selected boxes. The edit is sent with `gh issue edit --body-file -`,
the bytes on stdin from memory, so gh reads no file. <stem>.after.md keeps a copy of what was
sent. After the edit it reads the body back and compares, and on a mismatch prints the command
that restores the backup. No file is read and written at once: the body is held in memory, the
backup and the record of the edit are each written once from bytes that passed the guards, and
the read-back is compared in memory. A helper that read and wrote one file in one shell
expression got an empty file to read, sent it up, and blanked eleven issue bodies.

Two runs on one machine never interleave: each run holds an flock on
<lock-dir>/issue-<n>.lock from the first read to the read-back, and waits up to
TICK_LOCK_WAIT_S seconds for it. The lock folder does not depend on the backup folder, so two
runs with different --backup-dir values still share the lock. The lock name holds the issue
number only: the same number in two repositories waits its turn, which costs a moment and
harms nothing. Just before the edit it reads the body once more and refuses if
it changed since the backup, so a box someone else ticked meanwhile is not undone. That second
read narrows the window and cannot close it: GitHub has no conditional update, so an edit made in
a browser or on another machine between that read and the edit is overwritten.

On success only the backup is kept. When a run exits 3, the .after.md file it sent is kept beside
the backup, and so is a .readback.md when the body read back differs from it. The files are
created with mode 0600 and the backup and lock folders, when this script creates them, with
0700: a private repository's issue body must not be readable by other users of the machine.
Each file is created new, with O_EXCL and O_NOFOLLOW: a file or symlink already at the name is
refused and left as it is, never written through or truncated. A backup or lock folder that
belongs to another user, that group or others can write in, or that is itself a symlink, is
refused before any gh call, since another user could plant a symlink there at the name of the
next .after.md. There is no override: give a private folder.

Each folder is opened once and checked on that descriptor, and every file in it is created and
removed through the descriptor, never by its path. A folder renamed away and replaced after the
check, by someone who can write in a parent, then neither receives this run's files nor supplies
one of its own. The restore command printed on exit 3 or on a stop names the .before.md by its
absolute path, for a person to run later: that path is trusted only as far as the folder is.
Keep the backup folder where only you can write, its parents included. The command also names
the issue's repository with --repo, read from the issue's url (owner/repo on github.com,
host/owner/repo elsewhere), so it cannot land on another repository's issue of the same number.
When gh gives no usable url and no --repo was passed, a line above the command says to run it
from the issue's repository. On a read-back that differs, the message asks for a comparison of
the read-back with the .after.md first: an edit by someone else just after this one looks the
same, and the restore, which replaces the whole body, is the last resort for a damaged body.

Exit codes: 0 done or nothing to do, 1 refused by a guard or by the selection, another run
            holds the issue, or gh could not be started before the edit, 2 usage, 3 the body
            read back differs from what was sent, or the edit failed and the body may have
            changed, 130 stopped by INT or TERM (after the cleanup). Once the edit call has started, the
            stop prints the restore command and keeps the backup and the .after.md file, since
            the edit may have landed.
Env: TICK_BACKUP_DIR   backup dir when --backup-dir is not given
                       (default ${XDG_STATE_HOME:-$HOME/.local/state}/claude-kit/issue-bodies)
     TICK_LOCK_DIR     folder of the per-issue locks
                       (default ${XDG_STATE_HOME:-$HOME/.local/state}/claude-kit/issue-locks)
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
import urllib.parse

# The one definition of a box line: optional space, quote marks, a bullet or an ordered marker,
# one to four spaces, then the brackets. Group 1 is the bracket character. box_states adds the
# context: no box inside a code fence or an HTML comment.
BOX_RE = re.compile(rb'[ \t\r\f\v]*(?:>[ \t]*)*(?:[-*+]|[0-9]+[.)])[ ]{1,4}\[([ xX])\] ')
# The quote marks before a fence or a comment: each ">" may follow up to three spaces and take
# one space after it.
QUOTE_RE = re.compile(rb'(?:[ ]{0,3}>[ ]?)*')
# A fence: spaces, then three or more backticks or tildes. Group 1 is the indent, group 2 the
# run of fence characters, group 3 the rest of the line (the info string of an opening fence).
# box_states allows up to three spaces of indent, counted from the content of the list item the
# fence sits in.
FENCE_RE = re.compile(rb'([ ]*)(`{3,}|~{3,})(.*)\Z', re.S)
# A list item's marker and the spaces after it, to know where its content starts.
ITEM_RE = re.compile(rb'([ ]*)(?:[-*+]|[0-9]+[.)])([ ]{1,4})(?=\S)')
COMMENT_RE = re.compile(rb'[ ]{0,3}<!--')
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

    No line inside a code fence or an HTML comment is a box. The fence rules are CommonMark's,
    which GitHub follows. A fence opens on three or more backticks or tildes, indented up to
    three spaces past the content of the list item it sits in, or inside a quote. A backtick
    fence does not open when its info string holds a backtick: ```npm install``` on a line of
    its own is inline code, not a fence. Only a line of the same character, at least as long,
    with nothing but spaces after it closes the fence, so a ~~~ line inside a ``` fence, or a
    ``` line inside a ```` fence, is code. A fence that never closes runs to the end of the body,
    or to the end of the quote it opened in. A comment opens with <!-- at the start of a line
    and runs to the line that holds -->. A one-line comment hides only its own line.
    """
    states = []
    fence = None        # (character, length, deepest indent, quote depth) of the open fence
    in_comment = False
    item = None         # where the content of the current list item starts, or None
    for line in lines:
        state = None
        quote = QUOTE_RE.match(line)
        depth, rest = quote.group(0).count(b'>'), line[quote.end():]
        if fence is not None and depth < fence[3]:
            fence = None    # the quote that held the fence has ended, and the fence with it
        if fence is not None:
            m = FENCE_RE.match(rest)
            if (m and depth == fence[3] and len(m.group(1)) <= fence[2]
                    and m.group(2)[:1] == fence[0] and len(m.group(2)) >= fence[1]
                    and not m.group(3).strip(SPACE)):
                fence = None
        elif in_comment:
            if b'-->' in line:
                in_comment = False
        else:
            reach = (item or 0) + 3
            m = FENCE_RE.match(rest)
            c = COMMENT_RE.match(rest)
            if (m and len(m.group(1)) <= reach
                    and not (m.group(2)[:1] == b'`' and b'`' in m.group(3))):
                fence = (m.group(2)[:1], len(m.group(2)), reach, depth)
            elif c:
                in_comment = b'-->' not in rest[c.end():]
            else:
                m = BOX_RE.match(line)
                if m:
                    state = m.group(1)
                it = ITEM_RE.match(rest)
                if it:
                    item = len(it.group(0))
                elif rest.strip(SPACE) and len(rest) - len(rest.lstrip(b' ')) < (item or 0):
                    item = None     # a line left of the item's content ends the list
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
    # The same definition of a box as the selection: a box line in a fence or a comment is not one.
    states = box_states(old)
    for number, a in enumerate(old, 1):
        if number > len(new):
            bad.append('BAD line %d: the edited body ends early' % number)
            break
        b = new[number - 1]
        if a == b:
            continue
        m = BOX_RE.match(a)
        if not m or states[number - 1] is None:
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

class GhMissing(Exception):
    """gh could not be started at all: nothing was asked of GitHub."""


def fetch_issue(issue, repo_args, quiet=False):
    """(body as stored, as bytes, url or None), or None when gh fails or prints no body.

    Raises GhMissing when gh cannot be started.
    """
    try:
        proc = subprocess.run(['gh', 'issue', 'view', issue] + repo_args + ['--json', 'body,url'],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL if quiet else None)
    except OSError as e:
        raise GhMissing(e.strerror or str(e))
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.decode('utf-8'))
        body = data['body'].encode('utf-8')
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        return None
    url = data.get('url')
    return body, url if isinstance(url, str) else None


def fetch(issue, repo_args, quiet=False):
    """The body as stored, as bytes, or None when gh fails, prints no body or cannot start."""
    try:
        got = fetch_issue(issue, repo_args, quiet)
    except GhMissing:
        return None
    return got[0] if got else None


REPO_PART_RE = re.compile(r'[A-Za-z0-9._-]+\Z')


def repo_from_url(url, issue):
    """The --repo value for the issue at url: owner/repo on github.com, host/owner/repo on
    another host. None when the url is missing or is not the url of that issue."""
    if not url:
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname:
        return None
    path = parts.path.strip('/').split('/')
    if (len(path) != 4 or path[2] not in ('issues', 'pull') or path[3] != issue
            or not all(REPO_PART_RE.match(p) for p in path[:2])):
        return None
    host = parts.hostname.lower()
    if parts.port:
        host += ':%d' % parts.port
    owner_repo = '%s/%s' % (path[0], path[1])
    return owner_repo if host == 'github.com' else '%s/%s' % (host, owner_repo)


def restore_lines(issue, repo, before_path):
    """The command that puts the backup back, pinned to the issue's repository and to the
    backup's absolute path. Without a repository it says where it must be run."""
    lines = []
    if not repo:
        lines.append('Run it from a clone of the repository #%s belongs to: gh did not give the '
                     "issue's url and no --repo was passed, so the command holds no repository."
                     % issue)
    lines.append('  gh issue edit %s%s --body-file %s' % (
        issue, ' --repo ' + shlex.quote(repo) if repo else '', shlex.quote(before_path)))
    return '\n'.join(lines)


# The per-issue lock.

def take_lock(dir_fd, name, path, wait_s):
    """Hold an flock on the file name in the folder dir_fd, waiting up to wait_s seconds.
    Returns the descriptor. path is the name to print."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
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
                           % (path, holder(dir_fd, name)))
            time.sleep(0.1)
            continue
        # The run before us removes the file before it lets go. If it did that after our open,
        # we hold a file nobody else will open: start again on the one at the path now.
        try:
            same = os.path.samestat(os.fstat(fd), os.stat(name, dir_fd=dir_fd,
                                                          follow_symlinks=False))
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


def holder(dir_fd, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        try:
            pid = os.read(fd, 64).strip().decode('ascii')
        finally:
            os.close(fd)
    except (OSError, UnicodeDecodeError):
        return 'unknown'
    return pid if pid.isdigit() else 'unknown'


class Run:
    """Files and the lock that cleanup handles when the run ends."""
    lock = None     # (folder descriptor, name, descriptor) of the held lock
    files = []      # (folder descriptor, name) of the files this run created, removed unless
                    # the edit went out
    folders = []    # descriptors of the backup and lock folders, closed at the end
    edited = False
    restore = None  # the restore command, from the moment the edit call starts until it is safe


class Interrupted(BaseException):
    """INT or TERM arrived."""


class Collision(Exception):
    """A file tick.py meant to create is already there."""


def create_new(dir_fd, name):
    """Create name in the folder dir_fd for this run alone, mode 0600, and return its descriptor.

    The name is looked up in the folder that was opened and checked, not by its path, so a
    folder renamed away and replaced afterwards neither receives the file nor supplies one.
    O_EXCL refuses a name that is taken and O_NOFOLLOW refuses a symlink, so a file planted at
    the name is never written through or truncated. Raises Collision when the name is taken.
    """
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=dir_fd)
    except FileExistsError:
        raise Collision(name)
    Run.files.append((dir_fd, name))
    os.fchmod(fd, 0o600)
    return fd


def write_new(dir_fd, name, data):
    """A new file only this user can read, holding data: a private issue body may be in it."""
    fd = create_new(dir_fd, name)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def open_private_dir(path, what):
    """Create the folder if needed (mode 0700), open it once and return the descriptor.

    Everything after this goes through the descriptor. A folder another user owns or can write
    in is refused: they could plant a file at a name this run is about to create, or read the
    bodies kept there. The last component must not be a symlink.
    """
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        raise Stop(1, 'tick.py: cannot create %s' % path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno == errno.ELOOP or os.path.islink(path):
            raise Stop(1, 'tick.py: refused: the %s %s is a symlink. Give the folder itself. '
                          'Nothing was edited.' % (what, path))
        raise Stop(1, 'tick.py: cannot open the %s %s: %s' % (what, path, e.strerror))
    Run.folders.append(fd)
    st = os.fstat(fd)
    if st.st_uid != os.geteuid():
        raise Stop(1, 'tick.py: refused: the %s %s belongs to another user. Use a folder of your '
                      'own. Nothing was edited.' % (what, path))
    if st.st_mode & 0o022:
        raise Stop(1, 'tick.py: refused: the %s %s is writable by other users (mode %03o). Make '
                      'it private (chmod go-w %s) or use another folder. Nothing was edited.'
                   % (what, path, st.st_mode & 0o777, shlex.quote(path)))
    return fd


def cleanup():
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        if not Run.edited:
            for dir_fd, name in Run.files:
                try:
                    os.unlink(name, dir_fd=dir_fd)
                except OSError:
                    pass
        Run.files = []
        if Run.lock:
            dir_fd, name, fd = Run.lock
            Run.lock = None
            try:
                os.unlink(name, dir_fd=dir_fd)
            except OSError:
                pass
            os.close(fd)
        for fd in Run.folders:
            os.close(fd)
        Run.folders = []
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def mismatch_message(issue, diff, before_path, after_path, back_path, restore):
    """Exit 3 after a read-back that differs. An edit by someone else just after this one looks
    the same, and a full restore would remove their text, so comparing comes first and the
    restore command comes last, as the step for a damaged body only."""
    lines = ['tick.py: the body of #%s read back differs from what was sent. An edit by someone '
             'else in the moment after this one looks the same.' % issue]
    lines += ['  ' + line for line in diff[:20]]
    lines += ['  before (the body as it was):  %s' % before_path,
              '  after (what was sent):        %s' % after_path,
              '  read-back (the body now):     %s' % back_path,
              'Compare the read-back with the after file before doing anything: the read-back may '
              "hold someone else's newer text, and a restore would remove it.",
              'Last resort, only for a body that is damaged. This replaces the whole body with '
              'the backup:',
              restore]
    return '\n'.join(lines)


def on_signal(signum, frame):
    raise Interrupted()


def interrupted_message(restore):
    """What to print when INT or TERM stops the run: the restore command once the edit call has
    started, since the edit may have landed, and nothing before that."""
    if not restore:
        return None
    return ('tick.py: stopped while the edit was under way, and the body may have changed. '
            'Check it first. If it is damaged, this replaces the whole body with the backup:\n%s'
            % restore)


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
        elif a in ('--repo', '-R'):
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
    Run.lock, Run.files, Run.folders, Run.edited, Run.restore = None, [], [], False, None
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
    # The folders and files hold issue bodies, private ones among them: only this user reads
    # them. A folder that already exists keeps its mode.
    bfd = open_private_dir(bdir, 'backup folder')
    # The lock lives in its own folder. Under the backup folder, two runs given different
    # --backup-dir values took different locks and could overwrite each other's edit.
    ldir = os.environ.get('TICK_LOCK_DIR') or state + '/claude-kit/issue-locks'
    lfd = open_private_dir(ldir, 'lock folder')
    lock_name = 'issue-%s.lock' % issue
    Run.lock = (lfd, lock_name, take_lock(lfd, lock_name, '%s/%s' % (ldir, lock_name),
                                          float(wait)))

    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    stem = 'issue-%s-%s' % (issue, stamp)
    k = 1
    while True:
        try:
            fd = create_new(bfd, stem + '.before.md')
            break
        except Collision:
            k += 1
            stem = 'issue-%s-%s-%d' % (issue, stamp, k)
        except OSError:
            raise Stop(1, 'tick.py: cannot write in %s' % bdir)
    before_name, after_name, back_name = (stem + '.before.md', stem + '.after.md',
                                          stem + '.readback.md')
    # Absolute, so the printed paths and the restore command work from any directory.
    adir = os.path.abspath(bdir)
    before_path, after_path, back_path = ('%s/%s' % (adir, n)
                                          for n in (before_name, after_name, back_name))

    try:
        got = fetch_issue(issue, repo_args)
    except GhMissing as e:
        os.close(fd)
        refuse('cannot start gh to read #%s (%s)' % (issue, e))
    if got is None:
        os.close(fd)
        refuse('cannot read the body of #%s' % issue)
    before, url = got
    # The restore command names the issue's own repository, from its url, so it cannot land on
    # another repository's issue of the same number when it is run from somewhere else.
    restore = restore_lines(issue, repo_from_url(url, issue) or repo, before_path)
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
    try:
        again = fetch_issue(issue, repo_args)
    except GhMissing as e:
        refuse('cannot start gh to read #%s again before the edit (%s)' % (issue, e))
    again = again[0] if again else None
    if again is None:
        refuse('cannot read the body of #%s again before the edit' % issue)
    if again != before:
        refuse('the body of #%s changed since it was read, run again to work from the new body'
               % issue)

    # 7. Edit, then believe only what reads back.
    try:
        write_new(bfd, after_name, after)
    except Collision:
        refuse('%s is already there, and tick.py never writes through or over a file it did not '
               'create. Remove it if it is yours, then run again' % after_path)
    Run.edited = True
    # From here a stop by INT or TERM prints the restore command: the edit may land even when gh
    # is killed halfway.
    Run.restore = restore
    # The body goes to gh on stdin, from memory. gh reads no path, so a backup folder swapped
    # after the check cannot hand it a body of someone else's. The .after.md file is the record
    # of what was sent.
    try:
        proc = subprocess.run(['gh', 'issue', 'edit', issue] + repo_args + ['--body-file', '-'],
                              input=after, stdout=subprocess.DEVNULL)
    except OSError as e:
        # gh did not start, so nothing was sent: an ordinary refusal before the edit.
        Run.edited = False
        Run.restore = None
        refuse('cannot start gh for the edit (%s), so nothing was sent' % (e.strerror or e))
    if proc.returncode != 0:
        back = fetch(issue, repo_args, quiet=True)
        if back == before:
            Run.edited = False
            Run.restore = None
            refuse('the edit call failed and the body is as it was')
        raise Stop(3, 'tick.py: the edit call failed and the body may have changed. Check it '
                      'first. If it is damaged, this replaces the whole body with the backup:\n%s'
                   % restore)
    back = fetch(issue, repo_args)
    if back is None:
        raise Stop(3, 'tick.py: edited #%s, but cannot read it back. Check it first. If it is '
                      'damaged, this replaces the whole body with the backup:\n%s'
                   % (issue, restore))
    if back != after:
        try:
            write_new(bfd, back_name, back)
            kept = back_path
        except (Collision, OSError):
            kept = '(not saved: %s was already there or could not be written)' % back_path
        diff = list(difflib.unified_diff(
            after.decode('utf-8', 'replace').splitlines(),
            back.decode('utf-8', 'replace').splitlines(), 'sent', 'read back', lineterm=''))
        raise Stop(3, mismatch_message(issue, diff, before_path, after_path, kept, restore))
    Run.restore = None
    try:
        os.unlink(after_name, dir_fd=bfd)   # created by this run, in the folder it checked
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
    except Interrupted:
        message = interrupted_message(Run.restore)
        if message:
            err(message)
        return 130
    finally:
        cleanup()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    sys.exit(main(sys.argv[1:]))
