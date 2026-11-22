#!/usr/bin/env python3
"""List the variable names in env files, and never a value.

Usage:
  env-names.py [<file>...]

With no file it reads every .env* file in the current directory. For each file it prints one line:

  <file>: NAME_ONE NAME_TWO ...

Why this is a script and not a grep: a value in quotes can run over several lines (a private key,
a JSON blob). A pattern that prints "the word at the start of each line" then prints the start of
every continuation line, which is part of the secret. This parser tracks an open quote and skips
those lines. It prints names only, it never evaluates the file, and nothing it reads from the
right of an equals sign reaches the output.

A name is what stands before the first equals sign of an assignment line: letters, digits and
underscores, not starting with a digit, with an optional "export " in front. Blank lines and
comments are skipped. A value may start with a double quote, a single quote or a backtick. Inside
double quotes and backticks a backslash escapes the next character. Inside single quotes nothing
is escaped.

Exit codes: 0 done (also when no env file exists), 2 a file that was named cannot be read.
"""
import glob
import re
import sys

ASSIGN = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$', re.S)


def closes(text, quote):
    """True when text holds the closing quote, honouring backslash escapes except in single quotes."""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and quote != "'":
            i += 2
            continue
        if ch == quote:
            return True
        i += 1
    return False


def names(lines):
    """Variable names of an env file, in order of first appearance."""
    found, seen, open_quote = [], set(), None
    for line in lines:
        line = line.rstrip('\r\n')
        if open_quote:
            # Inside a value that runs over several lines. Nothing here is a name.
            if closes(line, open_quote):
                open_quote = None
            continue
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        m = ASSIGN.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2).lstrip()
        if name not in seen:
            seen.add(name)
            found.append(name)
        if value[:1] in ('"', "'", '`') and not closes(value[1:], value[0]):
            open_quote = value[0]
    return found


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        sys.stderr.write(__doc__ or "")
        return 2
    files = argv or sorted(glob.glob('.env*'))
    status = 0
    for path in files:
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                found = names(fh)
        except OSError as err:
            sys.stderr.write(f'env-names: cannot read {path}: {err.strerror}\n')
            status = 2
            continue
        print(f'{path}: {" ".join(found)}' if found else f'{path}: (no variables)')
    if not files:
        print('no .env files here')
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
