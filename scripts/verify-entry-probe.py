#!/usr/bin/env python3
"""Verify that the UniXNU entry probe is really inside a boot image.

This exists because "the probe was added to build.sh" and "the probe is in the
boot image" are different claims, and they diverged twice: 9d2c207 and
5e9a0f3 both shipped _start unchanged while the build kept succeeding.  An
assert inside build.sh can be skipped, can check a different file than the one
that gets packed, or can run before the patch; this reads the finished article
instead.

What it checks, straight out of the packed payload volume:

  _start first word    must no longer be 0x140006F5 (the plain `b` to
                       _start_first_cpu).  The probe replaces it with a branch
                       into the stage code placed in the zero padding after it.
  padding after _start the probe writes its stage code there, so it must not
                       still be all zeros.

A changed _start with empty padding is the dangerous half state: the kernel
branches into zeros and dies earlier than an unprobed kernel would.

The volume walk is FAT12 with 8 sectors per cluster, a 512-entry root directory
and two FATs; names here are used only to descend (EFI -> UniXNU -> Payloads).

Usage: verify-entry-probe.py <boot.img>
Exit status 0 only when both checks pass.
"""

import struct
import sys
import zlib
from pathlib import Path

PROBE_ENTRY_VA = 0xFFFFFFF0073F0488   # LC_UNIXTHREAD pc / _start
ORIGINAL_WORD = 0x140006F5            # `b _start_first_cpu`
STAGE1_CAVE = 0xFFFFFFF0073F0500      # first cave after rebase by -0x45E0000
EXPECTED_BRANCH = 0x1400001E          # _start -> STAGE1_CAVE, as the probe writes it
TEXT_EXEC_VM = 0xFFFFFFF007238000
TEXT_EXEC_FILEOFF = 0x234000

ATTR_DIRECTORY = 0x10
ATTR_LFN = 0x0F
ATTR_ARCHIVE = 0x20

ROOT = [b"EFI", b"UNIXNU", b"PAYLOADS"]
KERNEL_NAME = b"KERNEL~1MAC"


class Volume:
    def __init__(self, data):
        self.data = data
        self.sectors_per_cluster = data[13]
        reserved = struct.unpack_from("<H", data, 14)[0]
        fats = data[16]
        self.root_entries = struct.unpack_from("<H", data, 17)[0]
        sectors_per_fat = struct.unpack_from("<H", data, 22)[0]
        self.data_start = (reserved + fats * sectors_per_fat +
                           (self.root_entries * 32) // 512)
        self.root_offset = (reserved + fats * sectors_per_fat) * 512

    def cluster_offset(self, cluster):
        return (self.data_start +
                (cluster - 2) * self.sectors_per_cluster) * 512

    def entries(self, offset):
        found = []
        limit = self.root_entries if offset == self.root_offset else 1024
        for index in range(limit):
            raw = self.data[offset + index * 32:offset + (index + 1) * 32]
            if len(raw) < 32 or raw[0] == 0:
                break
            found.append({
                "name": raw[0:11],
                "attr": raw[11],
                "cluster": struct.unpack_from("<H", raw, 26)[0],
                "size": struct.unpack_from("<I", raw, 28)[0],
            })
        return found

    def find(self, offset, name):
        for entry in self.entries(offset):
            if entry["attr"] in (ATTR_DIRECTORY, ATTR_ARCHIVE) and \
                    entry["name"][:len(name)] == name:
                return entry
        return None

    def path(self, parts):
        offset = self.root_offset
        entry = None
        for part in parts:
            entry = self.find(offset, part)
            if entry is None:
                raise SystemExit("payload volume has no %s" % "/".join(parts))
            offset = self.cluster_offset(entry["cluster"])
        return entry


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    blob = Path(sys.argv[1]).read_bytes()

    compressed = struct.unpack_from("<I", blob, 8)[0]
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
        blob[4096:4096 + compressed])

    mark = stream.find(b"TB321FUESP")
    if mark < 0:
        raise SystemExit("no payload volume label in the kernel stream")
    volume = Volume(stream[mark - 43:])

    kernel_entry = volume.path(ROOT + [KERNEL_NAME])
    if kernel_entry["size"] <= 1_000_000:
        raise SystemExit("payload volume has no kernel.macho")
    start = volume.cluster_offset(kernel_entry["cluster"])
    kernel = volume.data[start:start + kernel_entry["size"]]

    where = TEXT_EXEC_FILEOFF + (PROBE_ENTRY_VA - TEXT_EXEC_VM)
    cave = TEXT_EXEC_FILEOFF + (STAGE1_CAVE - TEXT_EXEC_VM)
    entry = struct.unpack_from("<I", kernel, where)[0]
    padding = struct.unpack_from("<8I", kernel, cave)

    print("kernel.macho      %d bytes" % len(kernel))
    print("_start            file %#x  0x%08X  %s"
          % (where, entry, "patched" if entry != ORIGINAL_WORD else "ORIGINAL"))
    print("stage-1 cave      file %#x  %s"
          % (cave, " ".join("%08X" % w for w in padding)))

    if entry == ORIGINAL_WORD:
        print("FAIL: entry probe did not install (_start is the original branch)")
        return 1
    if entry != EXPECTED_BRANCH:
        print("FAIL: _start is 0x%08X but the probe writes 0x%08X (branch to %#x)"
              % (entry, EXPECTED_BRANCH, STAGE1_CAVE))
        return 1
    if not any(padding):
        print("FAIL: the stage-1 cave at file %#x is empty" % cave)
        return 1
    print("PASS: entry probe is in the image (_start branches to the stage-1 cave)")
    print()
    print("Next: flash this image and watch the panel.  DarwinBoot draws the green")
    print("bar; stage 1 draws a BLUE bar one 1/16th band below it once the kernel")
    print("entry actually runs.  Stage 1 begins with `ldr x1, [x0, #0x28]`, i.e.")
    print("boot_args->Video[0], so a blue bar also proves the args pointer and the")
    print("framebuffer address are valid.  If the panel resets after the green bar")
    print("with no blue one, that load faulted -- check args pa and Video[0].")
    return 0


if __name__ == "__main__":
    sys.exit(main())
