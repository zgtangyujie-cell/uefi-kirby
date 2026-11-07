#!/usr/bin/env python3
"""Stop PE_create_console from reading the iBoot video console handoff.

On this board PE_create_console does:

    base  = ml_io_map_wcomb(0x3C0FC000, 0x4000);
    magic = *(uint32_t *)base;          <-- 0x3C0FC000 is not mapped, faults
    ...
    bzero(base, 0x4000);
    initialize_screen(...);             <-- tail call, sets up the framebuffer

0x3C0FC000 is the iBoot video console handoff; under `fastboot boot` that page
was never set up, so the load faults and the tablet resets right after
DarwinEnter.  A blunt `ret` at the top also skips initialize_screen, which is
why the kernel then had no console output at all (measured on 6d7a741).

So patch exactly two instructions and keep everything else:

    +0x48  ldr w8, [x0]        -> mov w8, #0     (never dereference base)
    +0x64  b.eq  <ok>          -> b   <ok>       (skip bzero of the bad page)

ml_io_map_wcomb, the two PE_state stores and the trailing initialize_screen
all still run.

Usage: patch-pe-console.py <kernel.macho>
"""

import struct
import sys
from pathlib import Path

SYMBOLS = ("_PE_create_console", "PE_create_console")
PATCHES = (
    (0x48, 0xB9400008, 0x52800008, "ldr w8,[x0] -> mov w8,#0"),
    (0x64, 0x54000180, 0x1400000C, "b.eq -> b (skip bzero)"),
)


def segments(data):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            yield vmaddr, filesize, fileoff
        off += cmdsize


def symbol_value(data, wanted):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    symtab = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x2:  # LC_SYMTAB
            symtab = struct.unpack_from("<IIII", data, off + 8)
        off += cmdsize
    if symtab is None:
        raise SystemExit("kernel has no LC_SYMTAB")
    symoff, nsyms, stroff, strsize = symtab
    for index in range(nsyms):
        strx, _ntype, _nsect, _ndesc, value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        if strx >= strsize:
            continue
        end = data.find(b"\0", stroff + strx)
        name = data[stroff + strx:end].decode("utf-8", "replace")
        if name in wanted:
            return value
    return None


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())

    value = symbol_value(data, SYMBOLS)
    if value is None:
        raise SystemExit("PE_create_console not found in the symbol table")

    for vmaddr, filesize, fileoff in segments(data):
        if vmaddr <= value < vmaddr + filesize:
            base = fileoff + (value - vmaddr)
            break
    else:
        raise SystemExit(f"no segment covers {value:#x}")

    changed = 0
    for offset, expected, replacement, why in PATCHES:
        where = base + offset
        current = struct.unpack_from("<I", data, where)[0]
        if current == replacement:
            print(f"  +{offset:#04x} already patched ({why})")
            continue
        if current != expected:
            raise SystemExit(
                f"+{offset:#04x}: expected {expected:#010x}, found {current:#010x}; "
                "kernel layout changed, refusing to patch blind"
            )
        struct.pack_into("<I", data, where, replacement)
        print(f"  +{offset:#04x}: {expected:#010x} -> {replacement:#010x}  ({why})")
        changed += 1

    if changed:
        path.write_bytes(data)
        print(f"PE_create_console at {value:#x}: {changed} instruction(s) patched")
    else:
        print(f"PE_create_console at {value:#x}: nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
