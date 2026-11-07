#!/usr/bin/env python3
"""NOP the PE_consistent_debug_inherit call inside _arm_init.

Measured on hardware: arm_init reaches arm_vm_init (stage 3 reset proves the MMU
enable), but the probe placed after PE_consistent_debug_inherit never fires, and
the probe placed after the earlier (conditional) patch_low_glo call does not
either.  Disassembly shows PE_consistent_debug_inherit is an unconditional bl
whose only early-exit conditions are two SecureDT lookups that should fail
cleanly because the ADT has no 'consistent-debug-root' property.

It still does not return, which points at the SecureDT walk itself.  Debug
inheritance is optional, so skip the call and let arm_init continue to
serial_init.

Call site: va 0xfffffff0079b3c74, file 0x9afc74, original 0x97fe4ffc
          (bl 0xfffffff007947c64).
"""

import struct
import sys
from pathlib import Path

CALL_SITE = 0x9AFC74
EXPECTED = 0x97FE4FFC
NOP = 0xD503201F


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    word = struct.unpack_from("<I", data, CALL_SITE)[0]
    if word == NOP:
        print("debug-inherit call already NOPed")
        return 0
    if word != EXPECTED:
        raise SystemExit(
            f"expected {EXPECTED:#010x} at {CALL_SITE:#x}, found {word:#010x}; "
            "kernel layout changed, refusing to patch blind"
        )
    struct.pack_into("<I", data, CALL_SITE, NOP)
    path.write_bytes(data)
    print(f"PE_consistent_debug_inherit call NOPed at {CALL_SITE:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
