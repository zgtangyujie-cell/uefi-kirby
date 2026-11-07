#!/usr/bin/env python3
"""Validate a unified diff before git apply sees it.

`git apply` rejects a patch whose hunk header counts do not match the body with
a bare "corrupt patch", pointing at the *next* file header, which is the least
useful possible error location.  This reports the real problem instead: for
every hunk it counts the actual ' ', '+' and '-' lines and compares them with
the `@@ -a,b +c,d @@` header.

Usage:
    check_patch.py <patch> [<patch> ...]

Exit status 0 when every hunk is consistent, 1 otherwise.
"""

import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    bad = 0
    for path in sys.argv[1:]:
        raw = open(path, "rb").read()
        if b"\r\n" in raw:
            print("%s uses CRLF line endings." % path)
            print("  git apply on a Linux runner treats the \\r as part of the line"
                  " content, so every context line will fail to match.")
            print("  fix: rewrite with LF (newline='\\n'), and/or add"
                  " '*.patch text eol=lf' to .gitattributes")
            bad += 1
        lines = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        print("%s  (%d lines)" % (path, len(lines)))
        prefix = ""
        hunk_no = 0
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("diff --git"):
                name = line.split(" b/")[-1] if " b/" in line else line
                print("  FILE %s" % name)
                prefix = name
                i += 1
                continue
            m = HUNK_RE.match(line)
            if not m:
                i += 1
                continue
            hunk_no += 1
            old_decl = int(m.group(2)) if m.group(2) else 1
            new_decl = int(m.group(4)) if m.group(4) else 1
            old_act = new_act = 0
            j = i + 1
            while j < len(lines) and not (lines[j].startswith("@@") or lines[j].startswith("diff --git")):
                body = lines[j]
                if body.startswith("-"):
                    old_act += 1
                elif body.startswith("+"):
                    new_act += 1
                elif body.startswith(" "):
                    old_act += 1
                    new_act += 1
                elif body == "" and j == len(lines) - 1:
                    # a trailing empty element from the final newline is not a line
                    pass
                else:
                    # "\ No newline at end of file" and anything else: not a count
                    pass
                j += 1
            status = "OK" if (old_act == old_decl and new_act == new_decl) else "MISMATCH"
            if status != "OK":
                bad += 1
            print("    hunk #%d at line %d: header -%d,+%d  actual -%d,+%d  %s"
                  % (hunk_no, i + 1, old_decl, new_decl, old_act, new_act, status))
            if status != "OK":
                want = "@@ -%d,%d +%d,%d @@ %s" % (
                    int(m.group(1)), old_act, int(m.group(3)), new_act,
                    line[m.end():].strip())
                print("      fix: %s" % want)
            i = j

    print()
    if bad:
        print("FAIL: %d problem(s) found -- see the messages above" % bad)
        return 1
    print("PASS: no CRLF, and every hunk header matches its body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
