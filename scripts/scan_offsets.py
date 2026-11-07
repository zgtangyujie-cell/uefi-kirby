#!/usr/bin/env python3
"""Re-scan the checkpoint offsets of a named function in the CURRENT kernel.

The hardcoded addresses in earlier notes (e.g. `_IOFindBSDRoot` at
`_bsd_init+0x6D4`) were measured on the 51,945,472-byte prelinked kernel.  A
19,104,408-byte non-prelinked build moves everything, so those offsets are
worthless.  This recomputes them from the kernel's own symbol table.

Usage:
    scan_offsets.py <kernel.macho> <function-symbol> [symbol ...]

Example:
    scan_offsets.py kernel.macho _bsd_init _throttle_init _IOFindBSDRoot _vfs_mountroot

Output is one line per call: site address, offset inside the function, and the
callee.  Both names you asked for and unnamed callees are shown, so you can spot
the interesting neighbours.
"""

import bisect
import struct
import sys

NOISE = {
    "_kprintf", "_kernel_debug_string_early", "_panic",
    "___ubsan_handle_sub_overflow_minimal",
    "___ubsan_handle_add_overflow_minimal",
    "___ubsan_handle_type_mismatch_v1",
    "___ubsan_handle_out_of_bounds",
    "___stack_chk_fail",
}


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


def make_file_offset(segs):
    def file_offset(va):
        for vm, vs, fo, fs in segs:
            if vm <= va < vm + min(vs, fs):
                return fo + (va - vm)
        return None
    return file_offset


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
def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    data = open(sys.argv[1], "rb").read()
    segs, symtab = segments(data)
    file_offset = make_file_offset(segs)
    names = read_symbols(data, symtab)
    starts = sorted(names)
    print("kernel %d bytes, %d symbols" % (len(data), len(names)))
    print()

    for want in sys.argv[2:]:
        base = None
        for address, name in names.items():
            if name == want:
                base = address
                break
        if base is None:
            print("%s: not in the symbol table" % want)
            continue
        i = bisect.bisect_right(starts, base)
        end = starts[i] if i < len(starts) else base + 0x4000
        print("=" * 78)
        print("%s  va=%#x  filesize=%d  size=%d" % (want, base, end - base, end - base))
        print("=" * 78)
        va = base
        rows = []
        while va < end:
            f = file_offset(va)
            if f is None:
                break
            w = struct.unpack_from("<I", data, f)[0]
            if (w >> 26) == 0b100101:
                imm = w & 0x3FFFFFF
                if imm & 0x2000000:
                    imm -= 0x4000000
                tgt = va + imm * 4
                callee = names.get(tgt, "")
                if callee not in NOISE:
                    rows.append((va, tgt, callee))
            va += 4
        for site, tgt, callee in rows:
            print("  +0x%03X  %#x -> %#x  %s"
                  % (site - base, site, tgt, callee or "(unnamed)"))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
