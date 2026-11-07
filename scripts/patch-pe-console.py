#!/usr/bin/env python3
"""Replace PE_create_console's first instruction with `ret`.

Why: on this board PE_create_console reads the iBoot video console handoff at
PA 0x3C0FC000 before it ever looks at boot_args->Video.  Under `fastboot boot`
that page was never initialised, so the load faults and the tablet resets right
after DarwinEnter -- exactly the symptom we measured.

The instruction sequence is in the built kernel:

    mov  w0, #0xc000
    movk w0, #0x3c0f, lsl #16     -> x0 = 0x3C0FC000
    bl   ...

UniXNU's elden device record measured the same thing and reports that replacing
the first instruction with `ret` lets arm_init reach machine_startup.  This
script finds the symbol through LC_SYMTAB, so it survives kernel rebuilds that
move the address.

Usage: patch-pe-console.py <kernel.macho>
"""

import struct
import sys
from pathlib import Path

RET = 0xD65F03C0
SYMBOLS = ("_PE_create_console", "PE_create_console")


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
            where = fileoff + (value - vmaddr)
            break
    else:
        raise SystemExit(f"no segment covers {value:#x}")

    old = struct.unpack_from("<I", data, where)[0]
    if old == RET:
        print(f"PE_create_console at {value:#x} is already ret")
        return 0

    struct.pack_into("<I", data, where, RET)
    path.write_bytes(data)
    print(f"PE_create_console va {value:#x} file {where:#x}: {old:#010x} -> {RET:#010x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
