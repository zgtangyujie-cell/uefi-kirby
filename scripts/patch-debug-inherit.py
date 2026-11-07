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

Entry: va 0xfffffff007947c64, file 0x943c64, original 0xd100c3ff (sub sp,sp,#0x30)
"""

import struct
import sys
from pathlib import Path

ENTRY = 0x943C64
EXPECTED = 0xD100C3FF
RET = 0xD65F03C0


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    word = struct.unpack_from("<I", data, ENTRY)[0]
    if word == RET:
        print("PE_consistent_debug_inherit already returns")
        return 0
    if word != EXPECTED:
        raise SystemExit(
            f"expected {EXPECTED:#010x} at {ENTRY:#x}, found {word:#010x}; "
            "kernel layout changed, refusing to patch blind"
        )
    struct.pack_into("<I", data, ENTRY, RET)
    path.write_bytes(data)
    print(f"PE_consistent_debug_inherit now returns immediately ({ENTRY:#x})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
