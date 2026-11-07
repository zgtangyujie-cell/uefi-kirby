#!/usr/bin/env python3
"""List every call site in a probe image that was rewritten, and flag any round
where more than one site was instrumented.

An entry-probe round must redirect exactly ONE call site (stage 4).  If two or
more sites are redirected, `--occurrence` or the cave reuse misbehaved, and any
"reset / no reset" reading for that round is unreliable.

Usage:
    verify_all_sites.py <boot.img> [site-hex ...]

With no explicit sites, it scans the two functions used by the bisect
(`_kernel_bootstrap` and `_kernel_bootstrap_thread`) for `bl` instructions that
have become `b <cave>`.
"""
import io
import struct
import sys
import zlib
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TEXT_EXEC_VM = 0xFFFFFFF007238000
TEXT_EXEC_FILEOFF = 0x234000
CAVES = (0xFFFFFFF0073F0500, 0xFFFFFFF0073F0560,
         0xFFFFFFF0073F05C0, 0xFFFFFFF0073F0620)

BOOTSTRAP = (0xFFFFFFF0072B8138, 0xFFFFFFF0072B8874)
BS_THREAD = (0xFFFFFFF00798A570, 0xFFFFFFF00798A9BC)
BSD_INIT = (0xFFFFFFF0076AFF14, 0xFFFFFFF0076B0904)


class Volume:
    def __init__(self, data):
        self.data = data
        self.spc = data[13]
        reserved = struct.unpack_from("<H", data, 14)[0]
        fats = data[16]
        self.root_entries = struct.unpack_from("<H", data, 17)[0]
        spf = struct.unpack_from("<H", data, 22)[0]
        self.data_start = reserved + fats * spf + (self.root_entries * 32) // 512
        self.root_offset = (reserved + fats * spf) * 512

    def cluster_offset(self, c):
        return (self.data_start + (c - 2) * self.spc) * 512

    def entries(self, offset):
        out = []
        for i in range(self.root_entries if offset == self.root_offset else 1024):
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
    comp = struct.unpack_from("<I", blob, 8)[0]
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
        blob[4096:4096 + comp])
    mark = stream.find(b"TB321FUESP")
    vol = Volume(stream[mark - 43:])
    off = vol.root_offset
    e = None
    for part in (b"EFI", b"UNIXNU", b"PAYLOADS", b"KERNEL~1MAC"):
        e = vol.find(off, part)
        if e is None:
            raise SystemExit("payload volume missing %r" % part)
        off = vol.cluster_offset(e["cluster"])
    s = vol.cluster_offset(e["cluster"])
    return vol.data[s:s + e["size"]]


def branch_target(va, word):
    imm = word & 0x3FFFFFF
    if imm & 0x2000000:
        imm -= 0x4000000
    return va + imm * 4


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    img = Path(sys.argv[1])
    kernel = load_kernel(img.read_bytes())
    print("%s : kernel %d bytes" % (img.name, len(kernel)))

    explicit = [int(a, 16) for a in sys.argv[2:]]
    if explicit:
        ranges = [(min(explicit), max(explicit) + 4, explicit)]
    else:
        ranges = [(BOOTSTRAP[0], BOOTSTRAP[1], None),
                  (BS_THREAD[0], BS_THREAD[1], None),
                  (BSD_INIT[0], BSD_INIT[1], None)]

    rewritten = []
    bl_count = 0
    for lo, hi, only in ranges:
        va = lo
        while va < hi:
            if only is not None and va not in only:
                va += 4
                continue
            f = TEXT_EXEC_FILEOFF + (va - TEXT_EXEC_VM)
            if f < 0 or f + 4 > len(kernel):
                va += 4
                continue
            w = struct.unpack_from("<I", kernel, f)[0]
            op = w >> 26
            if op == 0b100101:
                bl_count += 1
            elif op == 0b000101:
                tgt = branch_target(va, w)
                if tgt in CAVES:
                    rewritten.append((va, tgt))
            va += 4

    print("call sites scanned: %d  (bl found: %d)" % (
        sum((hi - lo) // 4 for lo, hi, _ in ranges), bl_count))
    print()
    if not rewritten:
        print("no call site redirects into the probe caves")
        print("RESULT: this image has NO stage-4 probe installed")
        return 1

    for va, tgt in rewritten:
        print("  0x%X  ->  cave %#x   REWRITTEN" % (va, tgt))
    print()
    if len(rewritten) > 1:
        print("WARNING: %d sites rewritten -- a round must instrument exactly one."
              % len(rewritten))
        print("         Any reset/no-reset reading from this image is unreliable.")
        return 2
    print("OK: exactly one call site instrumented, round reading is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
