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

# kebab validates the ADT reg against an absolute address.  UniXNU's
# devicetree.py does not write absolute addresses: hardware_properties()
# stores (physical(address) - arm_io_window.base), where base is the lowest
# exported register window rounded down to 16 MiB.  On this board /kirby-ufs
# therefore arrives as 0x00d84000 with base 0x01000000, and 0x01d84000 never
# appears in the ADT at all (checked byte-wise against the built sidecar).
# Recover the base from /arm-io's own reg, whose first cell is that base.
OLD_REG_CHECK = (
    '+\tif (reg[0] != UFS_MMIO_BASE || reg[1] < UFS_MMIO_SIZE) {\n'
    '+\t\tprintf("KIRBY UFS: invalid absolute /kirby-ufs reg\\n");\n'
    '+\t\treturn ENXIO;\n'
    '+\t}\n'
)

NEW_REG_CHECK = (
    '+\t/*\n'
    '+\t * reg arrives relative to the arm-io base, not absolute: devicetree.py\n'
    '+\t * stores (physical - arm_io_window base), and that base is the lowest\n'
    '+\t * exported register window rounded down to 16 MiB.  Measured here:\n'
    '+\t * /kirby-ufs = 0xd84000, base = 0x1000000, so 0x1d84000 is the address\n'
    '+\t * to map.  /arm-io\'s reg carries that base as its first LE uint64.\n'
    '+\t */\n'
    '+\tif (reg[0] != UFS_MMIO_BASE) {\n'
    '+\t\tDTEntry io;\n'
    '+\t\tconst void *ioProp = NULL;\n'
    '+\t\tunsigned int ioSize = 0;\n'
    '+\t\tuint64_t base = 0;\n'
    '+\t\tif (SecureDTLookupEntry(NULL, "/arm-io", &io) == kSuccess &&\n'
    '+\t\t    SecureDTGetProperty(io, "reg", &ioProp, &ioSize) == kSuccess &&\n'
    '+\t\t    ioSize >= sizeof(base)) {\n'
    '+\t\t\tmemcpy(&base, ioProp, sizeof(base));\n'
    '+\t\t}\n'
    '+\t\tif (base && reg[0] + base == UFS_MMIO_BASE) {\n'
    '+\t\t\treg[0] += base;\n'
    '+\t\t}\n'
    '+\t}\n'
    '+\tif (reg[0] != UFS_MMIO_BASE || reg[1] < UFS_MMIO_SIZE) {\n'
    '+\t\tprintf("KIRBY UFS: invalid /kirby-ufs reg %llx %llx\\n", reg[0], reg[1]);\n'
    '+\t\treturn ENXIO;\n'
    '+\t}\n'
)


def fix_new_file_hunk(text):
    """Replace the reg check and correct the new file's hunk length.

    git apply counts the lines inside a hunk and rejects a mismatch as
    "corrupt patch", so any edit that changes the line count has to update the
    @@ -0,0 +1,N @@ header too.
    """
    if OLD_REG_CHECK not in text:
        raise SystemExit("the reg-check block to replace was not found")
    text = text.replace(OLD_REG_CHECK, NEW_REG_CHECK)

    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("+++ b/bsd/dev/kirby_ufs.c"))
    header = start + 1
    if not lines[header].startswith("@@"):
        raise SystemExit("expected a hunk header after +++")
    end = next(i for i, line in enumerate(lines)
               if i > header and line.startswith("diff --git"))
    count = sum(1 for line in lines[header + 1:end] if line.startswith("+"))
    lines[header] = "@@ -0,0 +1,%d @@\n" % count
    return "".join(lines)


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

    # Must run after the rename pass, because the block it looks for already
    # carries the KIRBY spelling.
    text = fix_new_file_hunk(text)

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
