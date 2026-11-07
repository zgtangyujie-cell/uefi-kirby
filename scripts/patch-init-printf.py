#!/usr/bin/env python3
"""Switch PE_init_printf from the cons_ops path to _vcattach.

Why: on this board every PE_init_printf(0) call sets
PE_state+0x788 = _console_write_char, which dispatches through
cons_ops[cons_ops_index].  _switch_to_video_console -- the only function
that sets that index to 1 -- has zero call sites, so the index rests at
whatever the boot left it and text can end up going nowhere.

PE_init_printf(1) takes the other branch instead: a tail branch straight
into _vcattach, which sets the vc_attached flag, checks video_ready and
calls _initialize_screen(NULL, 5) itself.  That is the only w1=5 call
site in the whole kernel.

The single instruction to change, verified against the built kernel:

    0xFFFFFFF0079B3DA8   file 0x9AFDA8   0x52800000  mov w0, #0
                                        0x52800020  mov w0, #1

Both the ELF-ish Mach-O layout and the surrounding call order were
checked: the call sits right after `bl _PE_create_console` and just
before `bl _PE_init_printf`, so _vinfo is already filled when
_vcattach runs.

Usage: patch-init-printf.py <kernel.macho>
"""

import struct
import sys
from pathlib import Path

WANTED = 0x52800000   # mov w0, #0
REPLACE = 0x52800020   # mov w0, #1
TARGET_VA = 0xFFFFFFF0079B3DA8
SEC_NAME = "__TEXT_EXEC"


def segments(data):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = data[off + 8:off + 24].decode("ascii", "replace").strip("\x00")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, off + 24)
            yield name, vmaddr, vmsize, fileoff, filesize
        off += size


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)

    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())

    for name, vmaddr, vmsize, fileoff, filesize in segments(data):
        if name != SEC_NAME:
            continue
        if not (vmaddr <= TARGET_VA < vmaddr + filesize):
            raise SystemExit(f"target {TARGET_VA:#x} is outside {name}'s file data")
        where = fileoff + (TARGET_VA - vmaddr)
        break
    else:
        raise SystemExit(f"no {SEC_NAME} segment")

    old = struct.unpack_from("<I", data, where)[0]
    if old == REPLACE:
        print(f"already patched at file {where:#x}")
        return 0
    if old != WANTED:
        raise SystemExit(
            f"unexpected opcode at {where:#x}: {old:#010x} "
            f"(expected {WANTED:#010x}) -- kernel layout moved, patch not applied")

    struct.pack_into("<I", data, where, REPLACE)
    path.write_bytes(data)
    print(f"PE_init_printf call at va {TARGET_VA:#x} file {where:#x}: "
          f"{old:#010x} -> {REPLACE:#010x} (mov w0,#0 -> mov w0,#1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
