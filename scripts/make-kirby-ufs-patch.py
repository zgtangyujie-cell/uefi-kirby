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


# UniXNU's userdata layout puts a manifest at the start of the partition and
# the actual filesystems in 1 MiB-aligned windows after it:
#
#   0x000000  "SHNGROOT" + version + count + image_bytes
#   0x000018  window[0]: name[32], offset u64, size u64, block_size, flags, sha256
#   0x100000  window[0] itself (the OS APFS container)
#
# APFS looks for a container at offset 0 of whatever block device it is handed,
# so publishing the whole partition leaves the container unreachable.  Publish
# window[0] instead.  A partition without the manifest keeps the old behaviour,
# so Android's own userdata still works.
OLD_FIND_TAIL = (
    '+\tif (!error) {\n'
    '+\t\terror = ufs_find_partition(want);\n'
    '+\t}\n'
    '+\tif (error) {\n'
    '+\t\treturn error;\n'
    '+\t}\n'
    '+\n'
    '+\tsu.bmajor = bdevsw_add(-1, &kirby_ufs_bdevsw);\n'
)

NEW_FIND_TAIL = (
    '+\tif (!error) {\n'
    '+\t\terror = ufs_find_partition(want);\n'
    '+\t}\n'
    '+\tif (!error) {\n'
    '+\t\terror = kirby_ufs_apply_manifest();\n'
    '+\t}\n'
    '+\tif (error) {\n'
    '+\t\treturn error;\n'
    '+\t}\n'
    '+\n'
    '+\tsu.bmajor = bdevsw_add(-1, &kirby_ufs_bdevsw);\n'
)

MANIFEST_FUNCTION = (
    '+/*\n'
    '+ * Re-scope the published device to the root window of the UniXNU manifest.\n'
    '+ *\n'
    '+ * The manifest sits at the start of the partition (concepts/userdata):\n'
    '+ *   +0x00  "SHNGROOT", then version u32, count u32, image_bytes u64\n'
    '+ *   +0x18  window[0]: name[32], offset u64 (+0x38), size u64 (+0x40)\n'
    '+ * The windows themselves start at 0x100000 and are 1 MiB aligned.\n'
    '+ *\n'
    '+ * APFS looks for a container at offset 0 of the block device it is given,\n'
    '+ * so handing it the whole partition puts the container out of reach.\n'
    '+ * Publishing window[0] is what makes the container addressable.\n'
    '+ *\n'
    '+ * No manifest means the partition is something else (Android f2fs here);\n'
    '+ * leave first_block and nblocks alone and publish it whole.\n'
    '+ */\n'
    '+static int\n'
    '+kirby_ufs_apply_manifest(void)\n'
    '+{\n'
    '+\tconst uint8_t *b = (const uint8_t *)(su.dma + DMA_BOUNCE);\n'
    '+\tint error = ufs_read_blocks(su.first_block, 1);\n'
    '+\tif (error) {\n'
    '+\t\tprintf("KIRBY UFS: cannot read block 0 for the manifest check: %d\\n", error);\n'
    '+\t\treturn error;\n'
    '+\t}\n'
    '+\tif (memcmp(b, "SHNGROOT", 8) != 0) {\n'
    '+\t\treturn 0;\n'
    '+\t}\n'
    '+\tuint32_t version, count;\n'
    '+\tmemcpy(&version, b + 8, 4);\n'
    '+\tmemcpy(&count, b + 12, 4);\n'
    '+\tif ((version != 1 && version != 2) || count == 0 || count > 8) {\n'
    '+\t\tprintf("KIRBY UFS: unsupported manifest v%u with %u windows\\n", version, count);\n'
    '+\t\treturn ENXIO;\n'
    '+\t}\n'
    '+\tchar name[33];\n'
    '+\tuint64_t offset, size;\n'
    '+\tmemcpy(name, b + 24, 32);\n'
    '+\tname[32] = 0;\n'
    '+\tmemcpy(&offset, b + 56, 8);\n'
    '+\tmemcpy(&size, b + 64, 8);\n'
    '+\tif (!size || (offset % UFS_BLOCK) || (size % UFS_BLOCK)) {\n'
    '+\t\tprintf("KIRBY UFS: window \\"%s\\" is not block aligned (0x%llx/0x%llx)\\n", name, offset, size);\n'
    '+\t\treturn ENXIO;\n'
    '+\t}\n'
    '+\tuint64_t first = offset / UFS_BLOCK, blocks = size / UFS_BLOCK;\n'
    '+\tif (first + blocks > su.nblocks) {\n'
    '+\t\tprintf("KIRBY UFS: window \\"%s\\" runs past the partition\\n", name);\n'
    '+\t\treturn ENXIO;\n'
    '+\t}\n'
    '+\tprintf("KIRBY UFS: manifest v%u, %u window(s); publishing \\"%s\\" at +0x%llx, %llu MiB\\n",\n'
    '+\t    version, count, name, offset, size >> 20);\n'
    '+\tsu.first_block += first;\n'
    '+\tsu.nblocks = blocks;\n'
    '+\treturn 0;\n'
    '+}\n'
    '+\n'
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

    # The manifest reader goes just before ufs_take_over_host, so it can use
    # ufs_read_blocks (defined earlier) and stays out of the adopt path.
    anchor = '+static int\n+ufs_take_over_host(void)\n+{\n'
    if anchor not in text:
        raise SystemExit("could not find ufs_take_over_host to insert the manifest reader before")
    text = text.replace(anchor, MANIFEST_FUNCTION + anchor, 1)

    if OLD_FIND_TAIL not in text:
        raise SystemExit("the post-find_partition block was not found")
    text = text.replace(OLD_FIND_TAIL, NEW_FIND_TAIL)

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
