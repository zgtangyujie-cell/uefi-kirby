#!/usr/bin/env python3
"""Verify that a specific `bl` call site was rewritten by the entry probe.

`verify-entry-probe.py` only checks `_start` and the stage-1 cave.  That is
enough to know the probe ran, but not enough to trust a per-call checkpoint:
the probe replaces `bl target` with `b <cave>`, so a round whose call site was
never touched produces "no reset" for a reason that has nothing to do with the
kernel (this is how 9d2c207 / 5e9a0f3 / 35405bd wasted three flashes).

Given a boot image and the VA of the call site you asked the probe to
instrument, this reports whether that site now branches into probe padding, and
what the branch target is, so a "no reset" result can be classified:

  site rewritten   -> the probe fired; "no reset" means the checkpoint is not
                      established (death before it, or the callee does not
                      return).  Follow up with --reset-before on the same call.
  site untouched   -> the probe never instrumented this call; the round proved
                      nothing.  Rebuild before reading anything into it.

Usage:
    verify_call_site.py <boot.img> <call-site-hex> [<call-site-hex> ...]

Exit status is 0 only when every listed site was rewritten.
"""

import io
import struct
import sys
import zlib
from pathlib import Path

TEXT_EXEC_VM = 0xFFFFFFF007238000
TEXT_EXEC_FILEOFF = 0x234000

# A `b` (unconditional, opcode 0b000101) plus `nop` is what the probe writes
# when it redirects a call site; `bl` (opcode 0b100101) means untouched.
BRANCH_OP = 0b000101
CALL_OP = 0b100101
NOP = 0xD503201F


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
        limit = self.root_entries if offset == self.root_offset else 1024
        out = []
        for i in range(limit):
            raw = self.data[offset + i * 32:offset + (i + 1) * 32]
            if len(raw) < 32 or raw[0] == 0:
                break
            out.append({"name": raw[0:11], "attr": raw[11],
                        "cluster": struct.unpack_from("<H", raw, 26)[0],
                        "size": struct.unpack_from("<I", raw, 28)[0]})
        return out

    def find(self, offset, name):
        for e in self.entries(offset):
            if e["attr"] in (0x10, 0x20) and e["name"][:len(name)] == name:
                return e
        return None


def load_kernel(blob):
    compressed = struct.unpack_from("<I", blob, 8)[0]
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
        blob[4096:4096 + compressed])
    mark = stream.find(b"TB321FUESP")
    if mark < 0:
        raise SystemExit("no payload volume label in the boot image")
    vol = Volume(stream[mark - 43:])
    offset = vol.root_offset
    entry = None
    for part in (b"EFI", b"UNIXNU", b"PAYLOADS", b"KERNEL~1MAC"):
        entry = vol.find(offset, part)
        if entry is None:
            raise SystemExit("payload volume has no %r" % part)
        offset = vol.cluster_offset(entry["cluster"])
    start = vol.cluster_offset(entry["cluster"])
    return vol.data[start:start + entry["size"]]


def decode_branch(va, word):
    delta = word & 0x3FFFFFF
    if delta & 0x2000000:
        delta -= 0x4000000
    return va + delta * 4


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    kernel = load_kernel(Path(sys.argv[1]).read_bytes())
    sites = [int(a, 16) for a in sys.argv[2:]]

    bad = 0
    print("kernel.macho %d bytes, %d site(s)" % (len(kernel), len(sites)))
    for va in sites:
        f = TEXT_EXEC_FILEOFF + (va - TEXT_EXEC_VM)
        if not (0 <= f < len(kernel) - 8):
            print("  %#x  outside __TEXT_EXEC file data" % va)
            bad += 1
            continue
        word = struct.unpack_from("<I", kernel, f)[0]
        follow = struct.unpack_from("<I", kernel, f + 4)[0]
        op = word >> 26
        if op == CALL_OP:
            target = decode_branch(va, word)
            print("  %#x  0x%08X  bl -> %#x   UNTOUCHED (probe did not instrument this call)"
                  % (va, word, target))
            bad += 1
        elif op == BRANCH_OP:
            target = decode_branch(va, word)
            displaced = "nop" if follow == NOP else ("0x%08X" % follow)
            print("  %#x  0x%08X  b  -> %#x   REWRITTEN (next word: %s)"
                  % (va, word, target, displaced))
        else:
            print("  %#x  0x%08X  unexpected opcode 0b%06b" % (va, word, op))
            bad += 1

    print()
    if bad:
        print("FAIL: %d site(s) not instrumented -- this round proves nothing" % bad)
        return 1
    print("PASS: every listed call site was rewritten by the probe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
