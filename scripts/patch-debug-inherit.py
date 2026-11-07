#!/usr/bin/env python3
"""Make PE_consistent_debug_inherit return immediately.

Measured on hardware: arm_init reaches arm_vm_init (the stage-3 reset proves the
MMU enable), but the probe placed after PE_consistent_debug_inherit never fires.
Disassembly shows the function cannot block by design: it looks up /chosen, then
the property 'consistent-debug-root', and returns -1 if either lookup fails.  Our
ADT has no such property (searched the 13,044-byte sidecar), so it should fail
cleanly -- yet it does not return.

Debug inheritance is optional, so make the function a no-op.

Important: patch the FUNCTION ENTRY, not the call site.  The entry probe runs
first and rewrites that call site into a branch to its own cave; a later attempt
to NOP the call site sees the probe's branch (0x17e8f26b) instead of the original
bl and refuses to patch.  Patching the entry leaves the probe intact, so its
reset site still fires once control returns.

This used to hardcode file offset 0x943C64 (va 0xFFFFFFF007947C64).  Adding the
UFS driver moved the function: the build failed with

  expected 0xd100c3ff at 0x943c64, found 0x94000101; kernel layout changed

so the entry is looked up by symbol now.  The mapping for this kernel is
file_offset = va - __TEXT.vmaddr, with vmaddr 0xFFFFFFF007004000; that
reproduces the old value exactly (0xFFFFFFF007947C64 - 0xFFFFFFF007004000 =
0x943C64), and keeps working when the layout moves again.
"""

import shutil
import struct
import subprocess
import sys
from pathlib import Path

SYMBOL = "_PE_consistent_debug_inherit"
TEXT_VMADDR = 0xFFFFFFF007004000
EXPECTED = 0xD100C3FF          # sub sp, sp, #0x30
RET = 0xD65F03C0


def nm_path():
    candidates = [
        shutil.which("llvm-nm"),
        "/usr/lib/llvm-18/bin/llvm-nm",
        "/usr/lib/llvm-19/bin/llvm-nm",
        "/opt/homebrew/opt/llvm/bin/llvm-nm",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("llvm-nm not found; it ships with the LLVM used for the kernel build")


def symbol_va(kernel, name):
    listing = subprocess.run([nm_path(), "-n", str(kernel)],
                             capture_output=True, text=True, check=True).stdout
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    raise SystemExit(f"{name} is not in the kernel symbol table")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())

    va = symbol_va(path, SYMBOL)
    entry = va - TEXT_VMADDR
    if not 0 <= entry < len(data) - 4:
        raise SystemExit(f"{SYMBOL} at {va:#x} maps outside the kernel file")

    word = struct.unpack_from("<I", data, entry)[0]
    if word == RET:
        print(f"{SYMBOL} already returns ({va:#x} -> file {entry:#x})")
        return 0
    if word != EXPECTED:
        raise SystemExit(
            f"{SYMBOL} at va {va:#x} (file {entry:#x}) starts with {word:#010x}, "
            f"expected {EXPECTED:#010x}; refusing to patch a function we cannot identify"
        )
    struct.pack_into("<I", data, entry, RET)
    path.write_bytes(data)
    print(f"{SYMBOL} now returns immediately (va {va:#x}, file {entry:#x})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
