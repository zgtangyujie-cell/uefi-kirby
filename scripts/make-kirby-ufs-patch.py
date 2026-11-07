"""Turn UniXNU-kebab's UFS patch into a tb321fu one.

kebab is SM8250 and this board is SM8650, but the parts that matter are the
same: UFS_MMIO_BASE is already 0x01d84000 in both, and the local
sm8650.dtsi says ufshc@1d84000 / phy@1d80000 — identical windows.  What has to
change is only naming and one size:

  * kebab_ufs.*      -> kirby_ufs.*        (file, symbols, devfs node prefix)
  * /kebab-ufs       -> /kirby-ufs         (the ADT node the driver looks up)
  * UFS_MMIO_SIZE     0x30000 -> 0x3000    (kebab maps 192 KiB; sm8650.dtsi
                                            declares 0x3000 and the driver
                                            rejects a reg shorter than the
                                            constant, so they must agree)
  * "KEBAB UFS"      -> "KIRBY UFS"        (printf prefix, for the log)

The default partition name stays "userdata": that is what this board's GPT
calls it (measured, CHANNEL #328).

Run from the repository root:  python3 scripts/make-kirby-ufs-patch.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "third_party/kebab-ufs-10063.patch"
TARGET = ROOT / "devices/UniXNU-tb321fu/patches/xnu/kirby-ufs.patch"

REPLACEMENTS = [
    ("kebab_ufs", "kirby_ufs"),
    ("KEBAB UFS", "KIRBY UFS"),
    ("/kebab-ufs", "/kirby-ufs"),
    ("kebab-ufs", "kirby-ufs"),
    ("KEBAB", "KIRBY"),
    ("kebab", "kirby"),
]


def main():
    if not SOURCE.is_file():
        raise SystemExit("missing source patch: %s" % SOURCE)
    text = SOURCE.read_text(encoding="utf-8")

    # The size constant must match what sm8650.dtsi declares, or kirby_ufs_init
    # rejects the ADT node it was given.
    before = text
    text = text.replace("#define UFS_MMIO_SIZE   0x30000u",
                        "#define UFS_MMIO_SIZE   0x3000u")
    if text == before:
        raise SystemExit("UFS_MMIO_SIZE line not found; the source patch changed")

    for old, new in REPLACEMENTS:
        text = text.replace(old, new)

    # Keep the provenance visible without changing the file's line count: a
    # hunk header says "+1,852", and adding or removing a line inside the hunk
    # makes git report "corrupt patch" at the next diff --git line.
    text = text.replace(
        " * KIRBY internal UFS root device (read-only).",
        " * TB321FU (kirby) UFS root device (read-only); ported from kebab (SM8250).")

    # Strip any hunk that did not come from kebab's three files.
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    files = re.findall(r"(?m)^diff --git a/(\S+)", text)
    print("wrote %s (%d bytes)" % (TARGET, TARGET.stat().st_size))
    print("touches:", ", ".join(files))
    for line in text.splitlines():
        if "UFS_MMIO_SIZE" in line or "UFS_MMIO_BASE" in line:
            print("  ", line.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
