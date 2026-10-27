#!/usr/bin/env python3
"""Apply all known-good driver binary patches for Lenovo Legion Y700 Gen3 (kirby).

Each patch is applied to the stock binary and written next to it as
"<name>.patched.efi"; the matching .inf is switched over to reference it.

The offsets were reverse engineered from Project-Silicium/Device-Binaries
(giulia, same SM8650 SoC) and verified byte-for-byte against the stock kirby
binaries.  The two entry-stub patches (VcsDxe / RscDxe) are local to kirby.

Usage:  python apply_binary_patches.py [repo_root]
        (repo_root defaults to D:/uefi)
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/uefi")
DRV = ROOT / "Binaries/kirby"

# driver path relative to Binaries/kirby -> list of (offset, orig_hex, new_hex, why)
PATCHES = [
    ("QcomPkg/Drivers/VcsDxe/VcsDxe", [
        (0x1000, "1f0000f1c0050054", "000080d2c0035fd6",
         "entry stub mov x0,#0;ret - the driver that kills the panel"),
    ]),
    ("QcomPkg/Drivers/RscDxe/RscDxe", [
        (0x1000, "1f0000f1c0050054", "000080d2c0035fd6",
         "entry stub - lets DXE dispatch finish to BDS"),
    ]),
    ("QcomPkg/Drivers/ClockDxe/ClockDxe", [
        (0x7EF8, "dc090094", "e0031f2a", "skip DCDDisableDependencies (call site 2)"),
        (0xA810, "96ffff97", "e0031f2a", "skip DCDDisableDependencies"),
    ]),
    ("QcomPkg/Drivers/SPMIDxe/SPMIDxe", [
        (0x154C, "400500b4fd7bbaa9", "e0031f2ac0035fd6",
         "SPMI handle function -> mov w0,#0;ret (stops UEFI crashing)"),
    ]),
    ("QcomPkg/Drivers/PmicDxe/PmicDxeLa", [
        (0x8AA0, "fd7bbea9f30b00f9", "e0031f2ac0035fd6",
         "SPMI-fail function -> return EFI_SUCCESS"),
        (0x22B84, "fd7bbfa9fd030091", "e0031f2ac0035fd6",
         "dead-battery check -> return EFI_SUCCESS"),
    ]),
    ("QcomPkg/Drivers/UFSDxe/UFSDxe", [
        # Was a Sleep->Wakeup call swap at 0xA468, copied from giulia and never
        # run on kirby, because the firmware used to die in SEC before DXE. The
        # first time it actually executed, UFSDxe took a data abort (translation
        # fault) on 0x98000000 -- inside mpss_region, which the device tree
        # marks no-map. That patch also overwrote the cbnz that checked the call
        # result, so a failure fell through instead of retrying.
        #
        # Until the real cause is known, stub the entry the same way VcsDxe and
        # RscDxe are stubbed: DXE dispatch finishes instead of aborting. The
        # menu phase does not need the disk; UFS gets fixed separately.
        (0x1000, "1f0000f1c0050054", "000080d2c0035fd6",
         "entry stub mov x0,#0;ret - UFSDxe aborts on 0x98000000 before BDS"),
    ]),
    ("QcomPkg/Drivers/ButtonsDxe/ButtonsDxe", [
        (0x3E70, "4820", "a801", "power key -> ENTER"),
        (0x3E74, "d6", "ed", "power key -> ENTER (paired)"),
    ]),
    ("QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe", [
        (0x561C, "a801", "0d00", "ExitBootServices: no USB deinit"),
        (0x561F, "34", "14", "ExitBootServices: no USB deinit (paired)"),
    ]),
    ("QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe", [
        (0x3FF1, "10", "00", "mark device non-removable"),
    ]),
]


def patch_driver(rel, spots):
    efi = DRV / f"{rel}.efi"
    patched = DRV / f"{rel}.patched.efi"
    if not efi.is_file():
        print(f"  SKIP {rel}: {efi} not found")
        return False

    data = bytearray(efi.read_bytes())
    ok = True
    for off, orig, new, why in spots:
        want = bytes.fromhex(orig)
        if data[off:off + len(want)] != want:
            print(f"  FAIL {rel} @0x{off:X}: expected {orig}, "
                  f"found {data[off:off + len(want)].hex()}")
            ok = False
            continue
        data[off:off + len(want)] = bytes.fromhex(new)
        print(f"  OK   {rel} @0x{off:X}  ({why})")

    if ok:
        patched.write_bytes(data)
        print(f"       -> {patched.name}")
        inf = DRV / f"{rel}.inf"
        if inf.is_file():
            text = inf.read_text(encoding="utf-8", errors="replace")
            base = Path(rel).name
            if f"{base}.patched.efi" not in text:
                text = text.replace(f"{base}.efi", f"{base}.patched.efi")
                inf.write_text(text, encoding="utf-8")
                print(f"       {inf.name} -> patched")
    return ok


def main():
    if not DRV.is_dir():
        print(f"driver directory not found: {DRV}")
        return 1
    print(f"patching drivers under {DRV}\n")
    n_spots = sum(len(s) for _, s in PATCHES)
    n_drivers = sum(1 for rel, _ in PATCHES if (DRV / f"{rel}.efi").is_file())
    ok = sum(patch_driver(rel, spots) for rel, spots in PATCHES)
    print(f"\n{ok}/{len(PATCHES)} drivers patched ({n_spots} patch sites total).")
    return 0 if ok == len(PATCHES) else 1


if __name__ == "__main__":
    sys.exit(main())
