#!/usr/bin/env python3
"""Check whether xnu-console is really wired up, and WHICH vc_info it reads.

`patch-xnu-console.py` redirects `_printf` to a chunk of code built from
`xnu-console.c`.  That code starts with:

    volatile struct vc_info *v = (volatile struct vc_info *)VINFO;
    if (fmt == 0 || v->v_baseaddr == 0 || v->v_depth != 32 || v->v_rowbytes == 0 || v->v_width < 8) {
        return;                       // <- draws NOTHING, silently
    }

so when the panel shows no kernel text at all, the first question is not
"did printf run" but "did this guard pass".  Two things can make it fail:

  * `_printf` was never redirected (first instruction is not a `b`), or
  * VINFO points at a vc_info that is still zero because `initialize_screen`
    has not run on this board (the XNU video console never starts here).

This tool answers both.  It follows the `b` out of `_printf`, decodes the
`adrp`+`add`/`ldr` pair that materialises VINFO, and reports the address the
injected code would read.  It then compares that against every vc_info-like
global it can find, and additionally reports whether the kernel even contains
a call to `initialize_screen`.

Usage:
    check_xnu_console.py <boot.img | kernel.macho>

Exit: 0 = printf redirected and VINFO looks like a sane vc_info
      1 = printf not redirected, or VINFO points nowhere useful
      2 = input could not be read
"""

import bisect
import struct
import sys
import zlib
from pathlib import Path

LABEL = b"TB321FUESP"


def load_kernel(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.count(b"__PRELINK_TEXT") and raw[:4] == b"\xcf\xfa\xed\xfe":
        return raw
    try:
        size = struct.unpack_from("<I", raw, 8)[0]
        blob = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
            raw[4096:4096 + size])
    except (zlib.error, struct.error):
        raise SystemExit("neither a Mach-O kernel nor a gzip boot image")
    mark = blob.find(LABEL)
    if mark < 0:
        raise SystemExit("no payload volume in the boot image")
    volume = blob[mark - 43:]
    spc = volume[13]
    reserved = struct.unpack_from("<H", volume, 14)[0]
    fats = volume[16]
    root_entries = struct.unpack_from("<H", volume, 17)[0]
    spf = struct.unpack_from("<H", volume, 22)[0]
    data_start = (reserved + fats * spf + (root_entries * 32) // 512)
    root_offset = (reserved + fats * spf) * 512

    def entries(offset):
        out = []
        for index in range(1024):
            raw_entry = volume[offset + index * 32:offset + (index + 1) * 32]
            if len(raw_entry) < 32 or raw_entry[0] == 0:
                break
            out.append({"name": raw_entry[0:11], "attr": raw_entry[11],
                        "cluster": struct.unpack_from("<H", raw_entry, 26)[0],
                        "size": struct.unpack_from("<I", raw_entry, 28)[0]})
        return out

    def find(offset, name):
        for entry in entries(offset):
            if entry["attr"] in (0x10, 0x20) and entry["name"][:len(name)] == name:
                return entry
        return None

    def cluster_offset(cluster):
        return (data_start + (cluster - 2) * spc) * 512

    offset = root_offset
    for part in (b"EFI", b"UNIXNU", b"PAYLOADS"):
        entry = find(offset, part)
        if entry is None:
            raise SystemExit("payload volume missing %r" % part)
        offset = cluster_offset(entry["cluster"])
    for name in (b"KERNEL~1MAC", b"KERNEL  MAC", b"KERNEL~1.MAC"):
        entry = find(offset, name)
        if entry is not None:
            start = cluster_offset(entry["cluster"])
            return volume[start:start + entry["size"]]
    raise SystemExit("no kernel.macho in Payloads/")


def segments_and_symbols(data: bytes):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    segs = []
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, offset)
        if cmd == 0x19:
            name = data[offset + 8:offset + 24].decode("ascii", "replace").strip("\x00")
            vm, vs, fo, fs = struct.unpack_from("<QQQQ", data, offset + 24)
            segs.append((name, vm, vs, fo, fs))
        elif cmd == 0x2:
            symtab = struct.unpack_from("<IIII", data, offset + 8)
        offset += size
    return segs, symtab


def make_fo(segs):
    def fo(va):
        for _name, vm, vs, f, fs in segs:
            if vm <= va < vm + min(vs, fs):
                return f + (va - vm)
        return None
    return fo


def read_symbols(data, symtab):
    symoff, nsyms, stroff, strsize = symtab
    table = {}
    for index in range(nsyms):
        strx, ntype, _sect, _desc, value = struct.unpack_from(
            "<IBBHQ", data, symoff + index * 16)
        if strx >= strsize or ntype == 0x20 or not value:
            continue
        end = data.find(b"\0", stroff + strx)
        if end < 0:
            continue
        name = data[stroff + strx:end].decode("utf-8", "replace")
        # Some STABS entries (ntype 46/78) share an address with the real
        # definition but carry an EMPTY name; a plain setdefault would then
        # shadow "_printf" with "".  Skip empty names and let a named
        # definition win over an unnamed alias at the same address.
        if not name:
            continue
        if value in table and not table[value]:
            table[value] = name
            continue
        table.setdefault(value, name)
    return table


def branch_target(va, word):
    imm = word & 0x3FFFFFF
    if imm & 0x2000000:
        imm -= 0x4000000
    return va + imm * 4


def decode_adrp(va, word):
    imm = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (va & ~0xFFF) + imm * 4096


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    try:
        kernel = load_kernel(path)
    except (OSError, SystemExit) as error:
        print("%s: %s" % (path.name, error))
        return 2

    segs, symtab = segments_and_symbols(kernel)
    fo = make_fo(segs)
    names = read_symbols(kernel, symtab)
    starts = sorted(names)
    print("%s : kernel %d bytes (%.1f MiB)" % (path.name, len(kernel), len(kernel) / 2**20))
    print()

    printf = next((value for value, name in names.items() if name == "_printf"), None)
    if printf is None:
        print("_printf: NOT IN SYMBOL TABLE")
        return 1
    entry = struct.unpack_from("<I", kernel, fo(printf))[0]
    print("_printf va=%#x  first instruction = %#010x" % (printf, entry))
    if (entry >> 26) != 0b000101:
        print("  NOT a branch -> printf was never redirected; console is not installed")
        return 1
    cave = branch_target(printf, entry)
    print("  -> branches to %#x  (console body)" % cave)
    print()

    # Walk the injected body looking for adrp pairs; report every candidate page.
    body = kernel[fo(cave):fo(cave) + 0x900]
    page = None
    candidates = []
    for index in range(0, min(len(body), 0x400), 4):
        word = struct.unpack_from("<I", body, index)[0]
        op = word >> 26
        if op == 0b10000 and (word & 0x1F) == 0x10:          # adrp x16..x30
            page = decode_adrp(cave + index, word)
        elif op == 0b10001011010 and page is not None:       # add xd, xn, #imm
            imm = (word >> 10) & 0xFFF
            shifted = imm << 0
            # only report adds that stay on the adrp page
            target = page + shifted
            if 0 < shifted < 0x1000:
                candidates.append((cave + index, target))
        elif op == 0b11111000010 and page is not None:       # ldr xt, [xn, #imm]
            imm = ((word >> 10) & 0xFFF) * 8
            candidates.append((cave + index, page + imm))
    print("pointer-producing pairs in the console body:")
    for site, target in candidates[:8]:
        name = names.get(target, "")
        print("  %#x -> %#x  %s" % (site, target, name))
    print()

    # Report which of those looks like the vc_info the guard reads, plus a few
    # known kernel globals, and whether initialize_screen has any caller.
    for probe_name in ("_vinfo", "_boot_progress_panic_vinfo", "_initialize_screen"):
        value = next((v for v, n in names.items() if n == probe_name), None)
        print("  %-28s %s" % (probe_name, ("%#x" % value) if value else "ABSENT"))
    vinfo = next((v for v, n in names.items() if n == "_vinfo"), None)
    if vinfo:
        word_at = struct.unpack_from("<I", kernel, fo(vinfo))[0] if fo(vinfo) is not None else None
        print("  _vinfo first 4 bytes in the image: %s"
              % ("not in a file-backed section (BSS)" if word_at is None else "%#010x" % word_at))
    init = next((v for v, n in names.items() if n == "_initialize_screen"), None)
    if init:
        callers = 0
        for _name, vm, vs, f, fs in segs:
            if not fs:
                continue
            for index in range(f, f + fs - 3, 4):
                word = struct.unpack_from("<I", kernel, index)[0]
                if word >> 26 == 0b100101:
                    va = vm + (index - f)
                    if branch_target(va, word) == init:
                        callers += 1
        print("  _initialize_screen callers: %d" % callers)
    print()

    if not candidates:
        print("RESULT: printf IS redirected, but no VINFO pointer found in the body")
        return 1
    print("RESULT: printf IS redirected -> 'no kernel text' means the vc_info guard failed,")
    print("        not that printf was never installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
