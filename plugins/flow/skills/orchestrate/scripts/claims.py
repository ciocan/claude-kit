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

Exit codes: 0 ok or clear, 1 others hold a claim (check only), 2 usage.
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


def claim_files(folder):
    """The *.claim entries of one folder, sorted, hidden ones included."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [folder + '/' + n for n in sorted(names) if n.endswith('.claim')]


def resource_folders(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [folder + '/' + n for n in sorted(names) if os.path.isdir(folder + '/' + n)]


def rows(paths):
    """Claim files as printable rows, oldest first."""
    now = int(time.time())
    out = []
    for path in paths:
        fields = {}
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            data = b''
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
    return [row for _, row in out]


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
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                die('cannot remove %s' % path)
            print('RELEASED %s for %s' % (res, owner))
        else:
            print('NO CLAIM %s for %s' % (res, owner))
        return 0

    if cmd == 'list':
        if res:
            files = claim_files(folder + '/' + res)
        else:
            files = [f for d in resource_folders(folder) for f in claim_files(d)]
        if not files:
            print('no claims on %s' % res if res else 'no claims')
        else:
            emit(rows(files))
        return 0

    # check
    others = [f for f in claim_files(folder + '/' + res)
              if os.path.basename(f) != owner + '.claim']
    if not others:
        print('CLEAR %s: no other claims' % res)
        return 0
    emit(rows(others))
    print('OTHERS HOLD %s: push the union of these refs and yours, or wait' % res)
    return 1


if __name__ == '__main__':
    # Refs and notes come from argv as given, bytes that are not UTF-8 included.
    sys.stdout.reconfigure(errors='surrogateescape')
    sys.exit(main(sys.argv[1:]))
