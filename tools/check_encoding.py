#!/usr/bin/env python3
"""Fail the build when a text asset contains mojibake or is not valid UTF-8.

Why this exists: PowerShell 5.1's Get-Content (ANSI/GBK on zh-CN Windows) piped into
Set-Content -Encoding UTF8 silently double-encodes every CJK character. This guard
makes such damage impossible to ship.

Detection rules (a single common character must NOT trip it - "路", "个", "错" are
perfectly normal words; double encoding shows up as *runs* of artefacts):

  1. UTF-8 BOM
  2. invalid UTF-8 byte sequences
  3. U+FFFD replacement character
  4. a rare "mojibake-only" Han character
  5. two or more suspicious characters in a row
  6. the classic replacement markers 锟斤拷 / 烫烫 / 屯屯

Usage: python tools/check_encoding.py <file> [<file> ...]
"""
import sys
import re

# Characters that essentially only show up as GBK<->UTF-8 double-encoding debris.
RARE = set("\ufffd\u8def\u7490\u71bb\u93cb\u8235\u9350\u93ba\u63b3\u9510\u9519\u4e2a\u546e\u7273")
# Common characters that are fine on their own but suspicious when they pile up.
SOFT = set("\u8def\u9519\u4e2a\u9510\u7490\u63b3")
MARKERS = ("\u951f\u65a4\u62f7", "\u70eb\u70eb", "\u5c6f\u5c6f")

HAN = re.compile(r"[\u3400-\u9fff]")


def suspicious(c):
    return c in RARE or c in SOFT


def check(path):
    raw = open(path, "rb").read()
    problems = []
    if raw[:3] == b"\xef\xbb\xbf":
        problems.append("UTF-8 BOM present (strip it)")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ["not valid UTF-8: %s" % exc]

    if "\ufffd" in text:
        problems.append("U+FFFD replacement character")

    for marker in MARKERS:
        if marker in text:
            problems.append("mojibake marker %s" % " ".join("U+%04X" % ord(c) for c in marker))

    runs = []
    i = 0
    n = len(text)
    while i < n:
        if suspicious(text[i]):
            j = i
            while j < n and suspicious(text[j]):
                j += 1
            if j - i >= 2:
                runs.append(text[i:j])
            i = j
        else:
            i += 1

    if runs:
        sample = runs[0][:6]
        problems.append("mojibake runs: %d (e.g. %r)" % (len(runs), sample))

    if not problems:
        # single rare artefact characters (not the common soft ones) still fail
        rare_hits = sorted({c for c in text if c in RARE and c not in SOFT and HAN.match(c)})
        if rare_hits:
            problems.append("rare mojibake chars: " + " ".join("U+%04X" % ord(c) for c in rare_hits))
    return problems


def main(argv):
    bad = 0
    for p in argv[1:]:
        probs = check(p)
        if probs:
            bad += 1
            print("FAIL %s: %s" % (p, "; ".join(probs)))
        else:
            print("OK   %s" % p)
    if bad:
        print("\n%d file(s) have encoding problems - fix them before building" % bad)
        return 1
    print("\nencoding check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))