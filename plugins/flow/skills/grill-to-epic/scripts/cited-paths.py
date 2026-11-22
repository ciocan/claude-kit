#!/usr/bin/env python3
"""Check that the paths a text cites exist on a git ref, before an issue or a brief sends an agent
to read them.

Usage:
  cited-paths.py <ref> [--repo <dir>] [--path <path>]... [<file>... | -]

  <ref>            the ref the agents' worktrees are cut from, for example origin/dev
  --repo <dir>     the repository to look in (default: the current directory)
  --path <path>    a path to check as given. Repeatable
  <file>... | -    texts to scan: an issue body, an epic, a brief. "-" reads stdin

A cited path is a word in backticks, or the target of a Markdown link, that looks like a file in
the repository: it has a slash and a file extension, or ends in a slash, or is a top-level
document such as README.md. A trailing :12 or #L12 is dropped. Commands, URLs, absolute paths,
globs and placeholders are skipped. Each path is checked once, in the order it first appears,
then the --path paths.

Prints OK or MISSING for each path, then a count. A missing path is fine only when the work
itself will create that file. A document an agent is told to read must be on the ref first:
a decision record left untracked in one checkout is in no worktree cut from the base.

Exit codes: 0 every cited path is on the ref (or none is cited), 1 at least one is missing,
            2 usage, or the ref or the repository cannot be read.
"""
import os
import re
import subprocess
import sys

# A word in backticks, or a Markdown link target. Neither holds a space.
CANDIDATE_RE = re.compile(rb'`[^` \n]+`|\]\([^) \n]+\)')
ANCHOR_RE = re.compile(rb'#.*\Z', re.S)
LINE_REF_RE = re.compile(rb':[0-9]+(?:-[0-9]+)?\Z')
TRAILING_PUNCT_RE = re.compile(rb'[.,;:]+\Z')
SKIP_START_RE = re.compile(rb'(?:/|~|\.\.|-|@|\$|<)')
SKIP_ANY_RE = re.compile(rb'[<>*{}$()=|"\\ ]')
EXT_RE = re.compile(rb'\.[A-Za-z0-9]+\Z')
TOP_DOC_RE = re.compile(rb'[A-Za-z0-9_.-]+\.(?:md|json|toml|yaml|yml|txt|lock)\Z')


def usage():
    sys.stderr.write(__doc__)
    sys.exit(2)


def die2(message):
    sys.stderr.write('cited-paths.py: %s\n' % message)
    sys.exit(2)


def candidates(text):
    """Words in backticks and Markdown link targets, in order of appearance."""
    out = []
    for m in CANDIDATE_RE.finditer(text.replace(b'\r', b'')):
        c = m.group(0)
        # The four trims run one after the other on every candidate, as the sed that did this
        # before ran them.
        if c.startswith(b'`'):
            c = c[1:]
        if c.endswith(b'`'):
            c = c[:-1]
        if c.startswith(b']('):
            c = c[2:]
        if c.endswith(b')'):
            c = c[:-1]
        out.append(c)
    return out


def as_path(word):
    """The word cleaned, when it looks like a path in this repository, else None."""
    p = ANCHOR_RE.sub(b'', word, count=1)            # an anchor or a #L12 line reference
    p = LINE_REF_RE.sub(b'', p, count=1)             # a :12 or :12-20 line reference
    p = TRAILING_PUNCT_RE.sub(b'', p, count=1)       # punctuation that followed the word
    if p.startswith(b'./'):
        p = p[2:]
    if not p or SKIP_START_RE.match(p):
        return None
    if b'://' in p or SKIP_ANY_RE.search(p):
        return None
    if p.endswith(b'/'):                             # a directory
        return p
    if b'/' in p and EXT_RE.search(p):               # dir/file.ext
        return p
    if TOP_DOC_RE.match(p):                          # a top-level document
        return p
    return None


def cited_paths(text):
    """The paths a text cites, cleaned, each once, in order of appearance."""
    paths = []
    for word in candidates(text):
        p = as_path(word)
        if p is not None and p not in paths:
            paths.append(p)
    return paths


def git(repo, *args):
    return subprocess.run(['git', '-C', repo] + list(args), stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        usage()
    ref, rest = argv[0], argv[1:]
    repo = '.'
    paths, files = [], []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == '--repo':
            if i + 1 >= len(rest):
                die2('--repo needs a directory')
            repo = rest[i + 1]
            i += 2
        elif a == '--path':
            if i + 1 >= len(rest) or not rest[i + 1]:
                die2('--path needs a path')
            paths.append(os.fsencode(rest[i + 1]))
            i += 2
        elif a in ('-h', '--help'):
            usage()
        elif a == '-':
            files.append(a)
            i += 1
        elif a.startswith('-'):
            die2('unknown option: %s' % a)
        else:
            files.append(a)
            i += 1
    if not paths and not files:
        die2('nothing to check: give a file, - for stdin, or --path')

    if git(repo, 'rev-parse', '--git-dir') != 0:
        die2('not a git repository: %s' % repo)
    if git(repo, 'rev-parse', '--verify', '--quiet', ref + '^{commit}') != 0:
        die2('no such ref in %s: %s (fetch first?)' % (repo, ref))
    texts = []
    for f in files:
        if f == '-':
            texts.append(sys.stdin.buffer.read())
            continue
        try:
            with open(f, 'rb') as fh:
                texts.append(fh.read())
        except OSError:
            die2('cannot read %s' % f)

    found = cited_paths(b'\n'.join(texts)) if files else []
    for p in paths:
        if p not in found:
            found.append(p)
    if not found:
        print('no paths cited')
        return 0

    missing = 0
    sys.stdout.flush()
    for p in found:
        spec = os.fsencode(ref) + b':' + (p[:-1] if p.endswith(b'/') else p)
        on_ref = subprocess.run([b'git', b'-C', os.fsencode(repo), b'cat-file', b'-e', spec],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if on_ref.returncode == 0:
            sys.stdout.buffer.write(b'OK       ' + p + b'\n')
        else:
            sys.stdout.buffer.write(b'MISSING  ' + p + b'\n')
            missing += 1
    sys.stdout.buffer.flush()
    print('%d cited, %d missing on %s' % (len(found), missing, ref))
    if missing:
        print('A missing path is fine only when the work will create it. A document an agent is '
              'told to read must be on %s first.' % ref)
        return 1
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(errors='surrogateescape')
    sys.exit(main(sys.argv[1:]))
