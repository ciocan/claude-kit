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

A name is what stands before the first "=" or ":" of an assignment line, with an optional
"export " in front. Blank lines and comments are skipped. A quote may open anywhere in a value
(TOKEN=prefix"first line), so every line is scanned to its end: double quotes, single quotes and
backticks.

Env files are read by different programs with different rules: a shell that sources the file, and
the dotenv libraries. They disagree on points that decide which lines belong to a value:

- whether a backslash escapes a single quote inside single quotes
- whether a backslash at the end of a line carries the value on to the next line
- whether a # starts a comment when it stands right after the "=" or at the start of a carried
  line

The parser does not pick one program. It follows every reading at once and keeps the set of
states they can be in. A line is listed only when every reading agrees that it stands outside
all values. A block between "-----BEGIN" and "-----END" is skipped as well, quoted or not.

So when in doubt the parser stays inside the value. A quote that never closes, or a point after
which the readings never agree again, hides the rest of the file, and a name may go unlisted.
No piece of a value is listed as a name.

Exit codes: 0 done (also when no env file exists), 2 a file that was named cannot be read.
"""
import glob
import re
import sys

ASSIGN = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*[=:](.*)$', re.S)
SEPARATOR = re.compile(r'[=:]')

OUTSIDE = None           # the reading stands outside every value
CONTINUES = 'continues'  # an unquoted backslash ended the line: the value goes on
QUOTES = ('"', "'", '`')


def scan(text, quote, escape_in_single, after_blank):
    """Walk through value text under one reading and return the state at its end.

    quote is the quote already open when the text starts, or None.
    escape_in_single says whether a backslash escapes the next character inside single quotes.
    after_blank says whether the text counts as standing after a blank. A # after a blank starts
    a comment, and a # right against the text before it is part of the value.
    Returns an open quote, CONTINUES or OUTSIDE.
    """
    i, prev = 0, (' ' if after_blank else 'x')
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\' and (quote != "'" or escape_in_single):
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == '\\':
            if i == len(text) - 1:
                return CONTINUES
            i += 2
            prev = 'x'
            continue
        elif ch in QUOTES:
            quote = ch
        elif ch == '#' and prev in (' ', '\t'):
            return OUTSIDE  # a comment: the rest of the line is not part of the value
        prev = ch
        i += 1
    return quote


def step(state, line):
    """Every state the readings can be in after this line, starting from one state."""
    if state in QUOTES:
        after = {scan(line, state, esc, False) for esc in (False, True)}
    else:
        if state is OUTSIDE:
            if not line.strip() or line.lstrip().startswith('#'):
                return {OUTSIDE}
            # A line that is no assignment may still open a quote, so it is scanned too.
            m = SEPARATOR.search(line)
            text = line[m.end():] if m else line
        else:
            text = line  # a carried line: all of it is more of the value
        # Whether a # at the very start is a comment is one of the points the programs differ on.
        after = {scan(text, None, esc, blank) for esc in (False, True) for blank in (False, True)}
    if CONTINUES in after:
        after.add(OUTSIDE)  # the reading of a program that does not join lines
    return after


def names(lines):
    """Variable names of an env file, in order of first appearance."""
    found, seen = [], set()
    states = {OUTSIDE}  # where the readings stand at the start of the line
    in_block = False    # between -----BEGIN and -----END
    for line in lines:
        line = line.rstrip('\r\n')
        if states == {OUTSIDE} and not in_block and line.strip() \
                and not line.lstrip().startswith('#'):
            m = ASSIGN.match(line)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                found.append(m.group(1))
        if in_block:
            if '-----END' in line:
                in_block = False
        elif '-----BEGIN' in line and '-----END' not in line.split('-----BEGIN', 1)[1]:
            in_block = True
        states = set().union(*(step(state, line) for state in states))
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
