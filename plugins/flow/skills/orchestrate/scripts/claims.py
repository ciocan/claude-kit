#!/usr/bin/env python3
"""Record what each session has deployed to a shared resource, so sessions that cannot message
each other can still see it before they push.

Usage:
  claims.py claim   <resource> <ref> [note...] [--owner <label>] [--dir <dir>]
  claims.py release <resource> [--owner <label>] [--dir <dir>]
  claims.py list    [<resource>] [--dir <dir>]
  claims.py check   <resource> [--owner <label>] [--dir <dir>]

A claim says "this session has deployed <ref> to <resource>". Several owners may hold claims on
one resource at once. Before a push, run check: it lists the other owners' claims, and you push
the union of their refs and yours, or wait. Each claim is one file, <dir>/<resource>/<owner>.claim,
with the lines owner=, resource=, ref=, time=, epoch=, host= and note=. Claiming again replaces
your own claim: the new file is written next to it and renamed over it, so a reader never sees
half a claim. Resource and owner use letters, digits, dot, dash and underscore. The ref is free
text on one line: a branch, a sha, a PR.

list and check print one claim per line, oldest first:
  <resource>  <owner>  <ref>  <time>  <age>  <note>

Env: CLAIMS_OWNER, else LOCK_OWNER, is the label when --owner is absent. CLAIMS_DIR is the folder
(default $XDG_STATE_HOME/claude-kit/claims, else ~/.local/state/claude-kit/claims). Keep it
outside any repository, so every worktree and session reads the same claims.

A folder that does not exist holds no claims. A folder that exists but cannot be listed is an
error, not an empty folder: check would otherwise print CLEAR over another owner's claim, and the
push that follows would overwrite their deployment. A claim file that cannot be read still names
its owner. check counts it as another owner's claim and exits 1, so the push waits, and says on
stderr which file it could not read. list prints it the same way and exits 2.

Exit codes: 0 ok or clear, 1 others hold a claim (check only), 2 usage, or a claims folder or
            claim file could not be read.
"""
import os
import random
import re
import socket
import sys
import time

NAME_RE = re.compile(r'[A-Za-z0-9._-]+\Z')
EPOCH_RE = re.compile(rb'[0-9]+\Z')


def usage():
    sys.stderr.write(__doc__)
    sys.exit(2)


def die(msg):
    sys.stderr.write('claims.py: %s\n' % msg)
    sys.exit(2)


def valid(name):
    return bool(NAME_RE.match(name)) and name not in ('.', '..')


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


def entries(folder):
    """The names in a folder. A folder that does not exist is empty. Any other failure stops
    the run: an unreadable folder may hold claims, and reading it as empty would hide them."""
    try:
        return sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    except OSError as e:
        die('cannot read the claims in %s: %s. Nothing was decided.' % (folder, e.strerror))


def claim_files(folder):
    """The *.claim entries of one folder, sorted, hidden ones included."""
    return [folder + '/' + n for n in entries(folder) if n.endswith('.claim')]


def resource_folders(folder):
    out = []
    for n in entries(folder):
        path = folder + '/' + n
        try:
            if os.stat(path).st_mode & 0o170000 == 0o040000:
                out.append(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            die('cannot read the claims in %s: %s. Nothing was decided.' % (path, e.strerror))
    return out


def rows(paths):
    """Claim files as printable rows, oldest first, and the files that could not be read.

    An unreadable claim still gets its row, named from its path, with the reason as its note.
    """
    now = int(time.time())
    out = []
    unreadable = []
    for path in paths:
        fields = {}
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            continue    # released between the listing and the read
        except OSError as e:
            unreadable.append('%s: %s' % (path, e.strerror))
            data = b''
            fields[b'note'] = os.fsencode('claim file unreadable: %s' % e.strerror)
        for line in data.split(b'\n'):
            for key in (b'ref', b'time', b'epoch', b'note'):
                if line.startswith(key + b'='):
                    fields[key] = line[len(key) + 1:]
        # The path is what check and release go by, so the names come from it.
        owner = os.path.basename(path)[:-len('.claim')]
        resource = os.path.basename(os.path.dirname(path))
        epoch = fields.get(b'epoch', b'')
        if EPOCH_RE.match(epoch):
            e = int(epoch)
            a = age(now - e)
        else:
            e = 0
            a = 'age unknown'
        row = b'  '.join([
            os.fsencode(resource), os.fsencode(owner), fields.get(b'ref') or b'-',
            fields.get(b'time') or b'unknown', a.encode(), fields.get(b'note') or b'-'])
        out.append((e, row))
    out.sort()
    return [row for _, row in out], unreadable


def report_unreadable(unreadable, what):
    for item in unreadable:
        sys.stderr.write('claims.py: cannot read %s. %s\n' % (item, what))


def emit(lines):
    sys.stdout.flush()
    for line in lines:
        sys.stdout.buffer.write(line + b'\n')
    sys.stdout.buffer.flush()


def main(argv):
    if len(argv) < 1:
        usage()
    cmd = argv[0]
    if cmd not in ('claim', 'release', 'list', 'check'):
        usage()
    args = argv[1:]

    env = os.environ
    home = env.get('HOME', '')
    state = env.get('XDG_STATE_HOME') or (home + '/.local/state' if home else '')
    folder = env.get('CLAIMS_DIR') or (state + '/claude-kit/claims' if state else '')
    owner = env.get('CLAIMS_OWNER') or env.get('LOCK_OWNER') or ''
    owner_given = False
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('--owner', '--dir'):
            if i + 1 >= len(args):
                usage()
            if a == '--owner':
                owner = args[i + 1]
                owner_given = True
            else:
                folder = args[i + 1]
            i += 2
        elif a == '--':
            pos.extend(args[i + 1:])
            break
        elif a in ('-h', '--help') or a.startswith('--'):
            usage()
        else:
            pos.append(a)
            i += 1

    if cmd == 'claim' and len(pos) < 2:
        usage()
    if cmd in ('release', 'check') and len(pos) != 1:
        usage()
    if cmd == 'list':
        if len(pos) > 1:
            usage()
        if owner_given:
            die('list takes no --owner')
    if pos and not valid(pos[0]):
        die("bad resource name '%s': use letters, digits, dot, dash, underscore" % pos[0])
    if cmd != 'list':
        if not owner:
            die('an owner label is required: pass --owner <label> or set CLAIMS_OWNER\n'
                '(or LOCK_OWNER). Every command runs in a new shell, so only the label tells '
                'your claim apart.')
        if not valid(owner):
            die("bad owner label '%s': use letters, digits, dot, dash, underscore" % owner)
    if not folder:
        die('no claims folder: set CLAIMS_DIR or HOME, or pass --dir')
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        die('cannot create the claims folder %s' % folder)

    res = pos[0] if pos else ''
    if cmd == 'claim':
        ref = pos[1]
        if not ref:
            die('the ref is empty')
        if '\n' in ref:
            die('the ref must be one line')
        note = ' '.join(pos[2:]).replace('\n', ' ')
        d = folder + '/' + res
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            die('cannot create %s' % d)
        now = time.time()
        stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))
        host = env.get('HOSTNAME') or socket.gethostname() or 'unknown'
        text = os.fsencode('owner=%s\nresource=%s\nref=%s\ntime=%s\nepoch=%d\nhost=%s\nnote=%s\n'
                           % (owner, res, ref, stamp, int(now), host, note))
        tmp = '%s/.%s.claim.tmp.%d.%d' % (d, owner, os.getpid(), random.randrange(1 << 30))
        try:
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            try:
                view = memoryview(text)
                while view:
                    view = view[os.write(fd, view):]
            finally:
                os.close(fd)
            os.replace(tmp, d + '/' + owner + '.claim')
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            die('cannot write the claim in %s' % d)
        print('CLAIMED %s for %s at %s: %s' % (res, owner, stamp, ref))
        return 0

    if cmd == 'release':
        path = folder + '/' + res + '/' + owner + '.claim'
        try:
            os.unlink(path)
        except FileNotFoundError:
            print('NO CLAIM %s for %s' % (res, owner))
            return 0
        except OSError as e:
            die('cannot remove %s: %s' % (path, e.strerror))
        print('RELEASED %s for %s' % (res, owner))
        return 0

    if cmd == 'list':
        if res:
            files = claim_files(folder + '/' + res)
        else:
            files = [f for d in resource_folders(folder) for f in claim_files(d)]
        lines, unreadable = rows(files)
        if not lines:
            print('no claims on %s' % res if res else 'no claims')
            return 0
        emit(lines)
        if unreadable:
            report_unreadable(unreadable, 'Its row above shows only what its name tells.')
            return 2
        return 0

    # check
    others = [f for f in claim_files(folder + '/' + res)
              if os.path.basename(f) != owner + '.claim']
    lines, unreadable = rows(others)
    if not lines:
        print('CLEAR %s: no other claims' % res)
        return 0
    emit(lines)
    report_unreadable(unreadable, 'It counts as that owner\'s claim: ask them before you push.')
    print('OTHERS HOLD %s: push the union of these refs and yours, or wait' % res)
    return 1


if __name__ == '__main__':
    # Refs and notes come from argv as given, bytes that are not UTF-8 included.
    sys.stdout.reconfigure(errors='surrogateescape')
    sys.exit(main(sys.argv[1:]))
