#!/usr/bin/env python3
"""Make serial_init() return 0 immediately.

Measured 2026-11-08 19:17 on image a02dc99c: the probe before
_PE_consistent_debug_inherit fires (2 s round trip through the bootloader), so
arm_vm_init and patch_low_glo both returned and the death is in the window
between line 532 and line 536 of osfmk/arm/arm_init.c:

  532  PE_consistent_debug_inherit();      already 0xD65F03C0 (ret), verified
                                            by parsing the kernel inside that
                                            image at file 0x945E2C
  #if __arm64__ && WITH_CLASSIC_S2R        not built on this configuration
  535  const unsigned int serial_exists = serial_init();

so serial_init() is the only call left in that window.

pexpert/arm/pe_serial.c:792 opens with SecureDTFindEntry("name", "uart0" /
"gpio" / "aux", ...), which is the same SecureDT path that
PE_consistent_debug_inherit was dying in before it was no-op'd.  This board has
no UART at all, so returning 0 is also the correct answer rather than a
workaround: arm_init then keeps PE_kputc on the video console, and
PE_init_kprintf takes its else branch.

Patch the FUNCTION ENTRY, not the call site.  The entry probe rewrites call
sites into branches to its own caves, and there are two callers anyway
(arm_init:535 and PE_init_kprintf), so a call-site patch would only fix one.
"""

import shutil
import struct
import subprocess
import sys
from pathlib import Path

SYMBOL = "_serial_init"
TEXT_VMADDR = 0xFFFFFFF007004000
MOV_W0_0 = 0x52800000          # mov w0, #0
RET = 0xD65F03C0               # ret
# A pacibsp / sub sp / stp / bti prologue; used only to refuse something that
# clearly is not a function entry.
PROLOGUES = (0xD503233F, 0xD503245F)


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


def looks_like_prologue(word):
    if word in PROLOGUES:
        return True
    # sub sp, sp, #imm   (0xD10xxxxx)   /   stp ... (0xA9xxxxxx)
    return (word & 0xFFC00000) == 0xD1000000 or (word & 0xFFC00000) == 0xA9000000


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())

    va = symbol_va(path, SYMBOL)
    entry = va - TEXT_VMADDR
    if not 0 <= entry < len(data) - 8:
        raise SystemExit(f"{SYMBOL} at {va:#x} maps outside the kernel file")

    first, second = struct.unpack_from("<II", data, entry)
    if first == MOV_W0_0 and second == RET:
        print(f"{SYMBOL} already returns 0 ({va:#x} -> file {entry:#x})")
        return 0
    if not looks_like_prologue(first):
        raise SystemExit(
            f"{SYMBOL} at va {va:#x} (file {entry:#x}) starts with {first:#010x}, "
            f"which is not a function prologue; refusing to patch"
        )
    struct.pack_into("<II", data, entry, MOV_W0_0, RET)
    path.write_bytes(data)
    print(f"{SYMBOL} now returns 0 (va {va:#x}, file {entry:#x}, was {first:#010x} {second:#010x})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
