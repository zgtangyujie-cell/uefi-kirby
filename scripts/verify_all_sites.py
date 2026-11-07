#!/usr/bin/env python3
"""List every call site in a probe image that was rewritten, resolving the
function ranges from the image's OWN symbol table.

An earlier version hardcoded the function addresses measured on the 51,945,472-byte
prelinked kernel; after the UFS driver landed, the kernel became 19,099,024 bytes,
every address moved, and the scan silently looked at the wrong code and reported
"no probe installed" for an image that had one.

Usage:
    verify_all_sites.py <boot.img> [function-symbol ...]

Default functions: _kernel_bootstrap, _kernel_bootstrap_thread, _bsd_init.
Exit status:
    0  exactly one call site rewritten (the round reading is valid)
    1  none rewritten (no stage-4 probe in this image)
    2  more than one rewritten (ambiguous; the reading is not trustworthy)
"""

import bisect
import struct
import sys
import zlib
from pathlib import Path

CAVES = (0xFFFFFFF0073F0500, 0xFFFFFFF0073F0560,
         0xFFFFFFF0073F05C0, 0xFFFFFFF0073F0620)
DEFAULT_FUNCTIONS = ("_kernel_bootstrap", "_kernel_bootstrap_thread", "_bsd_init")


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
    if mark < 0:
        raise SystemExit("no payload volume in the boot image")
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


def segments(data):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    segs = []
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x19:
            vm, vs, fo, fs = struct.unpack_from("<QQQQ", data, off + 24)
            segs.append((vm, vs, fo, fs))
        elif cmd == 0x2:
            symtab = struct.unpack_from("<IIII", data, off + 8)
        off += size
    return segs, symtab


def file_offset_of(segs, va):
    for vm, vs, fo, fs in segs:
        if vm <= va < vm + min(vs, fs):
            return fo + (va - vm)
    return None


def read_symbols(data, symtab):
    symoff, nsyms, stroff, strsize = symtab
    table = {}
    for i in range(nsyms):
        strx, ntype, _, _, value = struct.unpack_from("<IBBHQ", data, symoff + i * 16)
        # N_UNDF (32) is an undefined reference and always carries value 0; it
        # would otherwise shadow the real definition of a global.  Functions are
        # N_FUN (30) / 36 here, globals are N_SECT (15); keep everything except
        # N_UNDF and keep only entries with a real address.
        if strx >= strsize or ntype == 0x20 or not value:
            continue
        end = data.find(b"\0", stroff + strx)
        if end < 0:
            continue
        table.setdefault(value, data[stroff + strx:end].decode("utf-8", "replace"))
    return table
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
    segs, symtab = segments(kernel)
    if symtab is None:
        raise SystemExit("no LC_SYMTAB in the kernel")
    names = read_symbols(kernel, symtab)
    starts = sorted(names)
    wanted = sys.argv[2:] or list(DEFAULT_FUNCTIONS)

    print("%s : kernel %d bytes, %d symbols" % (img.name, len(kernel), len(names)))
    print()

    found = []
    scanned = 0
    for fn in wanted:
        base = None
        for address, name in names.items():
            if name == fn:
                base = address
                break
        if base is None:
            print("  %-32s not in the symbol table" % fn)
            continue
        i = bisect.bisect_right(starts, base)
        end = starts[i] if i < len(starts) else base + 0x4000
        sites = 0
        va = base
        while va < end:
            f = file_offset_of(segs, va)
            if f is None:
                break
            w = struct.unpack_from("<I", kernel, f)[0]
            if (w >> 26) == 0b000101:
                tgt = branch_target(va, w)
                if tgt in CAVES:
                    found.append((fn, va, tgt))
            sites += 1
            va += 4
        scanned += sites
        print("  %-32s %#10x .. %#10x  %5d words" % (fn, base, end, sites))

    print()
    print("scanned %d words in %d function(s)" % (scanned, len([w for w in wanted])))
    print()
    if not found:
        print("no call site redirects into a probe cave")
        print("RESULT: this image has NO stage-4 probe installed")
        return 1
    for fn, va, tgt in found:
        print("  %-32s %#x -> cave %#x   REWRITTEN" % (fn, va, tgt))
    print()
    if len(found) > 1:
        print("WARNING: %d sites rewritten -- a round instruments exactly one."
              % len(found))
        return 2
    print("OK: exactly one call site instrumented, round reading is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
