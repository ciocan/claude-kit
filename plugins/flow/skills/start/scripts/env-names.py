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
backticks. Outside quotes a # after a space starts a comment, and a backslash at the end of a
line carries the value on to the next line.

Env files are read by different programs with different rules, and the rules differ on one point
that matters here: whether a backslash escapes a single quote inside single quotes. A shell says
no, most dotenv libraries say yes. The parser keeps both readings. A line counts as outside every
value only when both readings agree that it is. A block between "-----BEGIN" and "-----END" is
skipped as well, quoted or not.

When in doubt the parser stays inside the value. A quote that never closes hides the rest of
the file, so a name may go unlisted. No piece of a value is listed as a name.

Exit codes: 0 done (also when no env file exists), 2 a file that was named cannot be read.
"""
import glob
import re
import sys

ASSIGN = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*[=:](.*)$', re.S)
SEPARATOR = re.compile(r'[=:]')


CONTINUES = 'continues'  # the value goes on to the next line: a backslash ended this one


def scan(text, quote, escape_in_single):
    """Walk through value text and say what is still open at its end.

    Returns the quote that is open, CONTINUES when an unquoted backslash ends the line, or None.
    quote is the quote already open when the text starts: a continuation line of a value.
    escape_in_single says whether a backslash escapes the next character inside single quotes.
    """
    i, prev = 0, ' '
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
        elif ch in ('"', "'", '`'):
            quote = ch
        elif ch == '#' and prev in (' ', '\t'):
            return None  # a comment: the rest of the line is not part of the value
        prev = ch
        i += 1
    return quote


def advance(quote, line, escape_in_single):
    """What one reading holds open after this line, given what it held open before it."""
    if quote == CONTINUES:
        return scan(line, None, escape_in_single)  # the whole line is more of the value
    if quote:
        return scan(line, quote, escape_in_single)
    if not line.strip() or line.lstrip().startswith('#'):
        return None
    # Scan what follows the first separator. A line that is no assignment may still open a quote.
    m = SEPARATOR.search(line)
    return scan(line[m.end():] if m else line, None, escape_in_single)


def names(lines):
    """Variable names of an env file, in order of first appearance."""
    found, seen = [], set()
    shell = dotenv = None   # the quote each reading holds open at the start of the line
    in_block = False        # between -----BEGIN and -----END
    for line in lines:
        line = line.rstrip('\r\n')
        outside = not shell and not dotenv and not in_block
        if outside and line.strip() and not line.lstrip().startswith('#'):
            m = ASSIGN.match(line)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                found.append(m.group(1))
        if in_block:
            if '-----END' in line:
                in_block = False
        elif '-----BEGIN' in line and '-----END' not in line.split('-----BEGIN', 1)[1]:
            in_block = True
        shell = advance(shell, line, False)
        dotenv = advance(dotenv, line, True)
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
